const fs = require('fs');
let content = fs.readFileSync('apps/desktop/src/components/VoiceOverlay.tsx', 'utf8');

content = content.replace(
    '    const stop = () => {',
    '    const stop = () => {\n      console.log("[DEBUG] executing stop()");'
);
fs.writeFileSync('apps/desktop/src/components/VoiceOverlay.tsx', content);
