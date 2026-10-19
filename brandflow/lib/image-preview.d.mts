export function imagePreviewHeaders(sha:string):Record<string,string>;
export function etagMatches(header:string|null,etag:string):boolean;
export function cachedImagePreview(sha:string):Promise<Buffer|null>;
export function createImagePreview(bytes:Buffer,sha:string):Promise<Buffer>;
