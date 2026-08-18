const fs = require('fs');
let content = fs.readFileSync('apps/desktop/src/components/VoiceOverlay.tsx', 'utf8');

content = content.replace(
    '    try {\n      stopAfterMinimumCapture();\n    } catch (e) { console.error("[DEBUG] Error in stopAfterMinimumCapture:", e); }\n    releaseRequested.current = true;\n    stopAfterMinimumCapture();',
    '    releaseRequested.current = true;\n    try { stopAfterMinimumCapture(); } catch (e) { console.error("[DEBUG] Error in stopAfterMinimumCapture:", e); }'
);
fs.writeFileSync('apps/desktop/src/components/VoiceOverlay.tsx', content);
