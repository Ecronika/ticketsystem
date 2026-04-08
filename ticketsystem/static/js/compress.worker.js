/**
 * Image compression Web Worker.
 *
 * Receives: { id, arrayBuffer, mimeType, fileName }
 * Posts back: { id, blob, fileName } on success
 *             { id, error }          on failure
 *
 * Uses createImageBitmap + OffscreenCanvas so the main thread is never
 * blocked during canvas resize / JPEG encoding.
 */

const MAX_SIZE = 1200;
const QUALITY = 0.8;

self.addEventListener('message', async function(e) {
    const { id, arrayBuffer, fileName } = e.data;
    try {
        const blob = new Blob([arrayBuffer]);
        const bitmap = await createImageBitmap(blob);

        let { width, height } = bitmap;
        if (width > height) {
            if (width > MAX_SIZE) { height = Math.round(height * MAX_SIZE / width); width = MAX_SIZE; }
        } else {
            if (height > MAX_SIZE) { width = Math.round(width * MAX_SIZE / height); height = MAX_SIZE; }
        }

        const canvas = new OffscreenCanvas(width, height);
        const ctx = canvas.getContext('2d');
        ctx.drawImage(bitmap, 0, 0, width, height);
        bitmap.close();

        const compressed = await canvas.convertToBlob({ type: 'image/jpeg', quality: QUALITY });
        // Always use .jpg extension since we compress to JPEG format
        const jpgFileName = fileName.replace(/\.[^.]+$/, '.jpg');
        self.postMessage({ id, blob: compressed, fileName: jpgFileName });
    } catch(err) {
        self.postMessage({ id, error: err.message });
    }
});
