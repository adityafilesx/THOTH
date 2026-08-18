const fs = require('fs');
let content = fs.readFileSync('apps/desktop/src/components/VoiceOverlay.tsx', 'utf8');

content = content.replace(
    '  const release = useCallback(() => {',
    '  const release = useCallback(() => {\n    console.log("[DEBUG] Release clicked!");\n    try {\n      stopAfterMinimumCapture();\n    } catch (e) { console.error("[DEBUG] Error in stopAfterMinimumCapture:", e); }'
);
content = content.replace(
    '  const stopAfterMinimumCapture = useCallback(() => {',
    '  const stopAfterMinimumCapture = useCallback(() => {\n    console.log("[DEBUG] stopAfterMinimumCapture called");'
);
content = content.replace(
    '    if (delay === 0) stop();',
    '    if (delay === 0) { console.log("[DEBUG] stopping immediately"); stop(); }'
);
content = content.replace(
    '    else stopTimer.current = window.setTimeout(stop, delay);',
    '    else { console.log("[DEBUG] stopping with delay", delay); stopTimer.current = window.setTimeout(stop, delay); }'
);
fs.writeFileSync('apps/desktop/src/components/VoiceOverlay.tsx', content);
