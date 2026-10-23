"""Local durable checkpoints and BrandFlow handoffs. Never dispatch Actions."""
import copy
import datetime as dt
import json
from pathlib import Path
from scheduler.native_runner import BATCH,read_api
from scheduler.native_worker import IST,NativeFailure,binding,stamp
from home_server.storage import write_state
from scripts.brandflow_sync import api_request,DEFAULT_API
from scripts.native_meta_handoff import record_receipt,record_published_outcomes
from home_server.fence import require_home

QUEUE=Path('/state/home-queue.json')


class LocalDispatcher:
    def __init__(self,config,state,persist):
        self.config,self.state,self.persist=config,state,persist

    def __call__(self,action,identifier,receipt=None):
        if action not in {'reserve','begin','receipt','published'}:
            raise NativeFailure('unsupported_worker_checkpoint')
        require_home(self.config)
        packet=read_api(self.config,'native-package',{'batchId':BATCH,'externalId':identifier})
        now=dt.datetime.now(IST)
        queue=json.loads(QUEUE.read_text())
        item=next((row for row in queue['items'] if row['id']==identifier),None)
        incoming=packet.get('nativeHandoff')
        if item is None:
            if action!='reserve':raise NativeFailure('unowned_submission_checkpoint')
            item={'id':identifier,'status':'approved','format':'image','platforms':packet['platforms'],
                  'caption':packet['caption'],'headline':packet['headline'],
                  'scheduled_at':stamp(packet['proposedSchedule']).isoformat(),
                  'delivery_mode':'meta_native','reviewed_content_hash':packet['contentHash']}
            queue['items'].append(item)
        expected=binding(packet)
        if item['scheduled_at']!=expected['scheduled_at'] or set(item['platforms'])!=set(expected['platforms']):
            raise NativeFailure('approval_changed_after_handoff')
        saved=item.get('native_handoff')
        if saved and saved.get('content_hash')!=packet['contentHash']:
            raise NativeFailure('approval_changed_after_handoff')
        if incoming is not None:
            if saved and (saved.get('content_hash')!=incoming['content_hash'] or saved.get('scheduled_at')!=incoming['scheduled_at']):
                raise NativeFailure('native_checkpoint_mismatch')
            # Recover a local write that reached BrandFlow before a restart.
            rank={'reserved':0,'submitting':1,'scheduled':2}
            if saved is None or rank[incoming['state']]>=rank[saved['state']]:
                item['native_handoff']=copy.deepcopy(incoming)
        handoff=item.get('native_handoff')
        if action=='reserve':
            if handoff is None:
                if stamp(packet['proposedSchedule'])<=now+dt.timedelta(minutes=10):
                    raise NativeFailure('approved_slot_too_close')
                item['native_handoff']={'state':'reserved','reserved_at':now.isoformat(),
                    'scheduled_at':expected['scheduled_at'],'content_hash':packet['contentHash'],
                    'platforms':packet['platforms'],'receipts':{}}
            elif handoff['state']!='reserved':raise NativeFailure('reservation_needs_reconciliation')
        elif action=='begin':
            if handoff is None:raise NativeFailure('unowned_submission_checkpoint')
            if handoff['state']=='reserved':
                handoff.update(state='submitting',submission_started_at=now.isoformat())
            elif handoff['state']!='submitting':raise NativeFailure('submission_checkpoint_unconfirmed')
        elif action=='receipt':
            previous=(handoff or {}).get('receipts',{}).get((receipt or {}).get('platform'))
            if previous:
                for field in ('schedule_id','content_hash','scheduled_at','platform'):
                    if previous.get(field)!=receipt.get(field):raise NativeFailure('conflicting_planner_schedule')
                receipt=previous
            record_receipt(item,receipt,now)
        else:record_published_outcomes(item,receipt,now)
        # Persist intent before transmitting. A failed POST is resumed using
        # the same immutable timestamps, never a second browser submission.
        write_state(QUEUE,queue)
        if action=='published':
            history=Path('/state/home-history.json')
            old=json.loads(history.read_text()) if history.exists() else {'topic_keys':[]}
            old['topic_keys']=sorted(set(old.get('topic_keys',[]))|{item.get('topic_key',identifier)})
            write_state(history,old)
        require_home(self.config)
        if action=='published':
            results={p:{'status':'published','postId':r['post_id'],'publishedAt':r['published_at']}
                     for p,r in item['platform_results'].items()}
            api_request('PUT',DEFAULT_API,self.config['draft_secret'],
                        {'batchId':BATCH,'externalId':identifier,'platformResults':results})
        else:
            result=api_request('POST',DEFAULT_API.rsplit('/',1)[0]+'/native-handoff',self.config['draft_secret'],
                {'batchId':BATCH,'externalId':identifier,'handoff':item['native_handoff']})
            if result.get('externalId')!=identifier or result.get('state')!=item['native_handoff']['state']:
                raise NativeFailure('submission_checkpoint_unconfirmed')
        key=action+':'+identifier+':'+(receipt or {}).get('platform','')
        job=self.state.setdefault('checkpoints',{}).setdefault(key,{})
        # Keep old run IDs as audit metadata; no old checkpoint is deleted.
        job.update(phase='success',backend='home')
        self.persist(self.state)
