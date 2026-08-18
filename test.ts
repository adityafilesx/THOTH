const fs = require('fs');
const content = fs.readFileSync('apps/desktop/src/lib/pcmRecorder.ts', 'utf8');
const fixed = content.replace('void this.context.close();\n    this.dispatchEvent(new Event("stop"));', 'try { void this.context.close(); } catch(e) { console.error("Close failed", e); }\n    this.dispatchEvent(new Event("stop"));');
fs.writeFileSync('apps/desktop/src/lib/pcmRecorder.ts', fixed);
console.log('Done');
