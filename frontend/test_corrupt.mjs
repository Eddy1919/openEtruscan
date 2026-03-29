import ort from 'onnxruntime-node';
import fs from 'fs';

fs.writeFileSync('fake.onnx', '<html><body>404 Not Found</body></html>');

try {
  await ort.InferenceSession.create('fake.onnx');
} catch (e) {
  console.log("ERROR RECEIVED:", e.message);
}
