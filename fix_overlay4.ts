const fs = require('fs');
let content = fs.readFileSync('apps/desktop/src/components/VoiceOverlay.tsx', 'utf8');

content = content.replace(
    '  const release = useCallback(() => {',
    '  const release = useCallback(() => {\n    console.log("[DEBUG-FIX] Release clicked! state:", state, "recorder state:", recorder.current?.state);'
);
content = content.replace(
    '    const stop = () => {',
    '    const stop = () => {\n      console.log("[DEBUG-FIX] executing stop()");'
);
content = content.replace(
    '      if (currentRecorder) flushAndStopRecorder(currentRecorder);',
    '      if (currentRecorder) { console.log("[DEBUG-FIX] calling flushAndStopRecorder"); flushAndStopRecorder(currentRecorder); } else { console.log("[DEBUG-FIX] recorder is null"); }'
);
content = content.replace(
    '        () => {\n          if (!cancelRequested.current) void finalise();\n        },',
    '        () => {\n          console.log("[DEBUG-FIX] stop event fired");\n          if (!cancelRequested.current) void finalise();\n        },'
);
content = content.replace(
    '    const finalise = useCallback(async () => {',
    '    const finalise = useCallback(async () => {\n      console.log("[DEBUG-FIX] finalise called, sessionId:", sessionId.current);'
);

fs.writeFileSync('apps/desktop/src/components/VoiceOverlay.tsx', content);
