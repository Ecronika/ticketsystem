/**
 * FileUploadManager — shared file upload module for ticket creation and detail pages.
 *
 * Handles: Web Worker image compression, Canvas fallback, drag & drop,
 * file staging gallery, and file count/size validation.
 *
 * All limits are passed via constructor — no hardcoded values.
 */
window.FileUploadManager = class FileUploadManager {
    /**
     * @param {Object} opts
     * @param {HTMLElement}  opts.dropzone    - The dropzone container element
     * @param {HTMLInputElement} opts.fileInput - The file <input> element
     * @param {HTMLElement}  opts.gallery     - Container for thumbnail previews
     * @param {HTMLElement}  opts.overlayEl   - Compression progress overlay
     * @param {HTMLElement}  opts.counterEl   - Compression counter text element
     * @param {string}       opts.workerUrl   - URL to compress.worker.js
     * @param {number}       opts.maxFileSize - Max size per file (bytes)
     * @param {number}       opts.maxTotalSize - Max total size (bytes)
     * @param {number}       opts.maxFiles    - Max number of files
     */
    constructor({ dropzone, fileInput, gallery, overlayEl, counterEl,
                  workerUrl, maxFileSize, maxTotalSize, maxFiles }) {
        this._dropzone = dropzone;
        this._fileInput = fileInput;
        this._gallery = gallery;
        this._overlayEl = overlayEl;
        this._counterEl = counterEl;
        this._maxFileSize = maxFileSize;
        this._maxTotalSize = maxTotalSize;
        this._maxFiles = maxFiles;

        this._files = [];
        this._isCompressing = false;
        this._dragCounter = 0;
        this._compressionIdCounter = 0;
        this._pendingCompressions = new Map();

        /** @type {function|null} Called whenever staged files change */
        this.onFilesChanged = null;

        // Init Web Worker
        const workerSupported = typeof Worker !== 'undefined' && typeof OffscreenCanvas !== 'undefined';
        this._worker = workerSupported && workerUrl ? new Worker(workerUrl) : null;
        if (this._worker) {
            this._worker.addEventListener('message', (e) => this._onWorkerMessage(e));
        }

        this._bindDropzone();
        this._bindFileInput();
    }

    // --- Public API ---

    get isCompressing() { return this._isCompressing; }
    getFiles() { return this._files.slice(); }
    getFileCount() { return this._files.length; }

    getTotalSize() {
        return this._files.reduce((sum, f) => sum + f.size, 0);
    }

    clearFiles() {
        this._files = [];
        this._renderGallery();
        if (this.onFilesChanged) this.onFilesChanged();
    }

    // --- Worker communication ---

    _onWorkerMessage(e) {
        const { id, blob, fileName, error } = e.data;
        const pending = this._pendingCompressions.get(id);
        if (!pending) return;
        this._pendingCompressions.delete(id);
        if (error) {
            pending.reject(new Error(error));
        } else {
            pending.resolve(new File([blob], fileName, {
                type: blob.type || 'image/jpeg',
                lastModified: Date.now()
            }));
        }
    }

    _compressViaWorker(file) {
        return new Promise((resolve, reject) => {
            const id = this._compressionIdCounter++;
            this._pendingCompressions.set(id, { resolve, reject });
            const reader = new FileReader();
            reader.onload = (ev) => this._worker.postMessage(
                { id, arrayBuffer: ev.target.result, mimeType: file.type, fileName: file.name },
                [ev.target.result]
            );
            reader.onerror = () => reject(new Error('File read error'));
            reader.readAsArrayBuffer(file);
        });
    }

    _compressViaCanvas(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = (event) => {
                const img = new Image();
                img.onload = () => {
                    const canvas = document.createElement('canvas');
                    let { width, height } = img;
                    const maxSize = 1200;
                    if (width > height) {
                        if (width > maxSize) { height *= maxSize / width; width = maxSize; }
                    } else {
                        if (height > maxSize) { width *= maxSize / height; height = maxSize; }
                    }
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext('2d');
                    ctx.drawImage(img, 0, 0, width, height);
                    canvas.toBlob((blob) => {
                        if (blob) {
                            resolve(new File([blob], file.name.replace(/\.[^.]+$/, '.jpg'), {
                                type: 'image/jpeg', lastModified: Date.now()
                            }));
                        } else {
                            reject(new Error('Canvas toBlob failed'));
                        }
                    }, 'image/jpeg', 0.8);
                };
                img.onerror = () => reject(new Error('Image load error'));
                img.src = event.target.result;
            };
            reader.onerror = () => reject(new Error('File read error'));
            reader.readAsDataURL(file);
        });
    }

    // --- File processing pipeline ---

    async processFiles(fileList) {
        const files = Array.from(fileList);
        if (files.length === 0) return;

        // Count check
        if (this._files.length + files.length > this._maxFiles) {
            if (window.showUiAlert) {
                window.showUiAlert(`Maximal ${this._maxFiles} Dateien erlaubt.`, 'warning');
            }
            return;
        }

        // Individual size check (pre-compression, only for non-images)
        for (const f of files) {
            if (!f.type.startsWith('image/') && f.size > this._maxFileSize) {
                if (window.showUiAlert) {
                    window.showUiAlert(
                        `"${f.name}" ist zu groß (max. ${Math.round(this._maxFileSize / 1024 / 1024)} MB).`,
                        'warning'
                    );
                }
                return;
            }
        }

        this._isCompressing = true;
        const imageCount = files.filter(f => f.type.startsWith('image/')).length;
        if (imageCount > 0 && this._overlayEl) {
            this._overlayEl.classList.remove('d-none');
        }
        let processed = 0;

        for (const file of files) {
            if (file.type.startsWith('image/')) {
                processed++;
                if (this._counterEl) {
                    this._counterEl.textContent = `${processed} / ${imageCount} Bilder`;
                }
                try {
                    const compressFn = this._worker
                        ? this._compressViaWorker.bind(this)
                        : this._compressViaCanvas.bind(this);
                    const result = await compressFn(file);
                    this._files.push(result instanceof File
                        ? result
                        : new File([result], file.name, { type: 'image/jpeg', lastModified: Date.now() })
                    );
                } catch (_e) {
                    // On compression failure, keep original
                    this._files.push(file);
                }
            } else {
                this._files.push(file);
            }
        }

        if (this._overlayEl) this._overlayEl.classList.add('d-none');

        // Total size check (post-compression)
        if (this.getTotalSize() > this._maxTotalSize) {
            if (window.showUiAlert) {
                window.showUiAlert(
                    `Gesamtgröße überschreitet das Limit (max. ${Math.round(this._maxTotalSize / 1024 / 1024)} MB).`,
                    'warning'
                );
            }
        }

        this._isCompressing = false;
        this._renderGallery();
        if (this.onFilesChanged) this.onFilesChanged();
    }

    // --- Drag & Drop ---

    _bindDropzone() {
        const dz = this._dropzone;
        if (!dz) return;

        dz.addEventListener('dragenter', (e) => {
            e.preventDefault();
            this._dragCounter++;
            dz.classList.add('border-primary', 'bg-primary-subtle');
        });
        dz.addEventListener('dragover', (e) => {
            e.preventDefault();
        });
        dz.addEventListener('dragleave', () => {
            this._dragCounter--;
            if (this._dragCounter <= 0) {
                this._dragCounter = 0;
                dz.classList.remove('border-primary', 'bg-primary-subtle');
            }
        });
        dz.addEventListener('drop', (e) => {
            e.preventDefault();
            this._dragCounter = 0;
            dz.classList.remove('border-primary', 'bg-primary-subtle');
            const files = e.dataTransfer?.files;
            if (files && files.length) {
                this.processFiles(files);
            }
        });
    }

    _bindFileInput() {
        if (!this._fileInput) return;
        this._fileInput.addEventListener('change', (e) => {
            const files = e.target.files;
            if (files && files.length) {
                this.processFiles(files);
            }
            this._fileInput.value = '';
        });
    }

    // --- Gallery rendering ---

    _renderGallery() {
        if (!this._gallery) return;
        this._gallery.innerHTML = '';
        this._files.forEach((file, index) => {
            const item = document.createElement('div');
            item.className = 'position-relative border rounded p-1 d-flex flex-column align-items-center justify-content-center bg-white shadow-sm';
            item.style.width = '100px';
            item.style.height = '100px';

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-sm btn-danger position-absolute top-0 end-0 rounded-circle p-0';
            removeBtn.style.width = '24px';
            removeBtn.style.height = '24px';
            removeBtn.style.transform = 'translate(50%, -50%)';
            removeBtn.innerHTML = '<i class="bi bi-x"></i>';
            removeBtn.addEventListener('click', () => {
                this._files.splice(index, 1);
                this._renderGallery();
                if (this.onFilesChanged) this.onFilesChanged();
            });

            if (file.type.startsWith('image/')) {
                const img = document.createElement('img');
                img.src = URL.createObjectURL(file);
                img.className = 'img-fluid object-fit-cover rounded';
                img.style.height = '100%';
                img.style.width = '100%';
                item.appendChild(img);
            } else {
                const icon = document.createElement('i');
                icon.className = 'bi bi-file-earmark-text fs-1 text-primary';
                const label = document.createElement('small');
                label.className = 'text-truncate mt-1 w-100 text-center';
                label.style.fontSize = '0.65rem';
                label.textContent = file.name;
                item.appendChild(icon);
                item.appendChild(label);
            }

            item.appendChild(removeBtn);
            this._gallery.appendChild(item);
        });
    }
};
