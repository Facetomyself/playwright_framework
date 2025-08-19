// core/init_scripts/get_fingerprint.js
async function getFingerprint() {
    const fingerprint = {};

    // 1. Navigator 对象
    try {
        fingerprint.navigator = {
            userAgent: navigator.userAgent || null,
            platform: navigator.platform || null,
            vendor: navigator.vendor || null,
            language: navigator.language || null,
            languages: navigator.languages || null,
            deviceMemory: navigator.deviceMemory || null,
            hardwareConcurrency: navigator.hardwareConcurrency || null,
            plugins: Array.from(navigator.plugins).map(p => ({ name: p.name, description: p.description, filename: p.filename })),
            mimeTypes: Array.from(navigator.mimeTypes).map(m => ({ type: m.type, description: m.description, suffixes: m.suffixes })),
        };
    } catch (e) {
        fingerprint.navigator = { error: e.toString() };
    }

    // 2. Screen 对象
    try {
        fingerprint.screen = {
            width: screen.width,
            height: screen.height,
            availWidth: screen.availWidth,
            availHeight: screen.availHeight,
            colorDepth: screen.colorDepth,
            pixelDepth: screen.pixelDepth,
        };
    } catch (e) {
        fingerprint.screen = { error: e.toString() };
    }

    // 3. WebGL
    try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (gl) {
            const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
            fingerprint.webgl = {
                vendor: gl.getParameter(gl.VENDOR),
                renderer: gl.getParameter(gl.RENDERER),
                unmaskedVendor: debugInfo ? gl.getParameter(debugInfo.UNMASKED_VENDOR_WEBGL) : 'N/A',
                unmaskedRenderer: debugInfo ? gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL) : 'N/A',
            };
        } else {
            fingerprint.webgl = null;
        }
    } catch (e) {
        fingerprint.webgl = { error: e.toString() };
    }

    // 4. Canvas 指纹
    try {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        const txt = 'BrowserLeaks,com <canvas> 1.0';
        ctx.textBaseline = 'top';
        ctx.font = "14px 'Arial'";
        ctx.textBaseline = 'alphabetic';
        ctx.fillStyle = '#f60';
        ctx.fillRect(125, 1, 62, 20);
        ctx.fillStyle = '#069';
        ctx.fillText(txt, 2, 15);
        ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
        ctx.fillText(txt, 4, 17);
        const dataUrl = canvas.toDataURL();
        // 使用简单的哈希函数
        let hash = 0;
        for (let i = 0; i < dataUrl.length; i++) {
            const char = dataUrl.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        fingerprint.canvasHash = hash;
    } catch (e) {
        fingerprint.canvasHash = { error: e.toString() };
    }

    return JSON.stringify(fingerprint, null, 2);
}