const fs = require('fs');
let content = fs.readFileSync('apps/desktop/src/lib/pcmRecorder.ts', 'utf8');

content = content.replace(
    '    this.source.disconnect();\n    this.processor.disconnect();\n    this.silentOutput.disconnect();',
    '    try { this.source.disconnect(); } catch(e) {}\n    try { this.processor.disconnect(); } catch(e) {}\n    try { this.silentOutput.disconnect(); } catch(e) {}'
);
fs.writeFileSync('apps/desktop/src/lib/pcmRecorder.ts', content);
