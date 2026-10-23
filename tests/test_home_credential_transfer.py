import base64
import json
import time
import unittest
from scripts.home_credential_transfer import encrypt,decrypt
from instagram_credentials import make_bundle


class TransferTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        cls.key=rsa.generate_private_key(public_exponent=65537,key_size=2048).private_bytes(
            serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())

    def values(self):
        now=int(time.time())
        return {'FUNZUG_INSTAGRAM_LOGIN_CREDENTIAL':json.dumps(make_bundle('fixture-not-a-real-token','123456',now-10,now+86400))}

    def test_roundtrip_and_no_plaintext(self):
        values=self.values(); envelope=encrypt(values,self.key)
        self.assertNotIn('fixture-not-a-real-token',json.dumps(envelope))
        self.assertEqual(decrypt(envelope,self.key),values)

    def test_tamper_rejected(self):
        envelope=encrypt(self.values(),self.key)
        data=bytearray(base64.b64decode(envelope['ciphertext']));data[0]^=1
        envelope['ciphertext']=base64.b64encode(data).decode()
        with self.assertRaises(Exception):decrypt(envelope,self.key)

    def test_expired_envelope_rejected(self):
        now=int(time.time());envelope=encrypt(self.values(),self.key,now-3700)
        with self.assertRaises(ValueError):decrypt(envelope,self.key,now)

    def test_unexpected_secret_name_refused(self):
        values=self.values();values['UNRELATED_SECRET']='fixture'
        with self.assertRaises(ValueError):encrypt(values,self.key)


if __name__=='__main__':unittest.main()
