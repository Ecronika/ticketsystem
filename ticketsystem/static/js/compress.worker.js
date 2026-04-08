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
    const { id, arrayBuffer, mimeType, fileName } = e.data;
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

        // Preserve transparency for PNGs; fill white background for JPEG conversion
        const isTransparent = mimeType === 'image/png' || mimeType === 'image/webp' || mimeType === 'image/gif';
        if (!isTransparent) {
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, width, height);
        }

        ctx.drawImage(bitmap, 0, 0, width, height);
        bitmap.close();

        let compressed, outFileName;
        if (isTransparent) {
            compressed = await canvas.convertToBlob({ type: 'image/png' });
            outFileName = fileName.replace(/\.[^.]+$/, '.png');
        } else {
            compressed = await canvas.convertToBlob({ type: 'image/jpeg', quality: QUALITY });
            outFileName = fileName.replace(/\.[^.]+$/, '.jpg');
        }
        self.postMessage({ id, blob: compressed, fileName: outFileName });
    } catch(err) {
        self.postMessage({ id, error: err.message });
    }
});
