/* Dedicated worker: OPFS sync access handles are only available here. */
const OPFS_SCHEMA_VERSION = 1;
const OPFS_FILE_NAME = 'viptrack-registrations-v1.json';
const MAX_REGISTRY_BYTES = 64 * 1024 * 1024;

function isRecordMap(value) {
    return value && typeof value === 'object' && !Array.isArray(value);
}

function validPayload(payload) {
    return payload && payload.schemaVersion === OPFS_SCHEMA_VERSION &&
        Number.isFinite(payload.generatedAt) && isRecordMap(payload.records);
}

async function readSyncFile(fileHandle) {
    let accessHandle;
    try {
        accessHandle = await fileHandle.createSyncAccessHandle();
        const size = accessHandle.getSize();
        if (!Number.isFinite(size) || size <= 0 || size > MAX_REGISTRY_BYTES) return null;
        const bytes = new Uint8Array(size);
        const read = accessHandle.read(bytes, { at: 0 });
        if (read !== size) return null;
        const payload = JSON.parse(new TextDecoder().decode(bytes));
        return validPayload(payload) ? payload : null;
    } catch (error) {
        return null;
    } finally {
        try { accessHandle?.close(); } catch (error) {}
    }
}

async function writeSyncFile(fileHandle, records) {
    let accessHandle;
    try {
        accessHandle = await fileHandle.createSyncAccessHandle();
        const bytes = new TextEncoder().encode(JSON.stringify({
            schemaVersion: OPFS_SCHEMA_VERSION,
            generatedAt: Date.now(),
            records
        }));
        if (bytes.byteLength > MAX_REGISTRY_BYTES) throw new Error('OPFS registry payload is too large');
        accessHandle.truncate(0);
        const written = accessHandle.write(bytes, { at: 0 });
        if (written !== bytes.byteLength) throw new Error('OPFS registry write was incomplete');
        accessHandle.flush();
    } finally {
        try { accessHandle?.close(); } catch (error) {}
    }
}

async function loadRegistry(message) {
    if (!self.navigator?.storage?.getDirectory) throw new Error('OPFS unavailable');
    const root = await self.navigator.storage.getDirectory();
    const fileHandle = await root.getFileHandle(OPFS_FILE_NAME, { create: true });
    const cached = await readSyncFile(fileHandle);
    if (cached && Date.now() - cached.generatedAt <= (message.maxAgeMs || 86400000)) {
        return { records: cached.records, warm: true };
    }

    const response = await fetch(message.compactUrl, {
        cache: 'no-store',
        credentials: 'same-origin'
    });
    if (!response.ok) throw new Error('Compact registry HTTP ' + response.status);
    const records = await response.json();
    if (!isRecordMap(records)) throw new Error('Compact registry is not an object');
    await writeSyncFile(fileHandle, records);
    return { records, warm: false };
}

self.onmessage = async event => {
    const message = event.data || {};
    if (message.type !== 'load' || !message.id) return;
    try {
        const result = await loadRegistry(message);
        self.postMessage({ type: 'loaded', id: message.id, ...result });
    } catch (error) {
        self.postMessage({
            type: 'error',
            id: message.id,
            code: error?.message === 'OPFS unavailable' ? 'unsupported' : 'load-failed',
            message: String(error?.message || error)
        });
    }
};
