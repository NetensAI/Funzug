export function contentHash(value:unknown):string;
export function reviewedMediaHash(draft:Record<string,any>):string;
export function draftContentHash(row:Record<string,any>):string|null;
export function draftContentHashFromChecksum(row:Record<string,any>):string|null;
export function storedOrderedMediaHash(row:Record<string,any>):string;
