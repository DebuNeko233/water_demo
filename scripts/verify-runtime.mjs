/** Validate a redistributable Windows CPython runtime, not merely python.exe.
 *
 * Called once on the staging copy and again against the actual packaged
 * Electron resources. Uses isolated Python, a restricted PATH, native-module
 * imports, and real OpenCV AVI/MP4 video read/write on the copied interpreter.
 */
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'

if (process.platform !== 'win32') {
  throw new Error('The bundled Python runtime validator is Windows-only')
}

const root = path.resolve(process.argv[2] ?? 'build/backend')
const manifestPath = path.join(root, 'manifest.json')
assert.ok(fs.existsSync(manifestPath), 'Bundled Python manifest missing: ' + manifestPath)
const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'))
assert.equal(typeof manifest.python, 'string')
const executable = path.resolve(root, manifest.python)
const relative = path.relative(root, executable)
assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative),
  'Manifest points outside the bundled backend')
const runtime = path.dirname(executable)
for (const item of [
  executable,
  path.join(runtime, 'python312.dll'),
  path.join(runtime, 'Lib', 'encodings', '__init__.py'),
  path.join(runtime, 'Lib', 'site-packages'),
]) {
  assert.ok(fs.existsSync(item), 'Incomplete Python distribution: ' + item)
}

const verification = `
import os, sys, json, importlib, pathlib, tempfile
base = pathlib.Path(sys.executable).resolve().parent
prefix = pathlib.Path(sys.prefix).resolve()
assert prefix == base, "Python prefix escaped packaged runtime: " + str(prefix)
modules = (
    'encodings', 'ctypes', '_ssl', '_sqlite3', 'ssl', 'bz2', 'lzma',
    'numpy', 'cv2', 'pydantic_core', 'fastapi', 'uvicorn', 'loguru',
    'sample_backend', 'sample_backend.main', 'sample_backend.services.video_stream',
)
for name in modules:
    module = importlib.import_module(name)
    location = getattr(module, '__file__', None)
    if location:
        resolved = pathlib.Path(location).resolve()
        assert resolved.is_relative_to(base), (
            name + ' unexpectedly loaded from external Python: ' + str(resolved)
        )
import numpy as np
import cv2
for extension, codec in (('.avi', 'MJPG'), ('.mp4', 'mp4v')):
    handle, filename = tempfile.mkstemp(suffix=extension)
    os.close(handle)
    try:
        writer = cv2.VideoWriter(filename, cv2.VideoWriter_fourcc(*codec), 10, (64, 64))
        assert writer.isOpened(), 'OpenCV could not initialize ' + codec + ' writer'
        writer.write(np.full((64, 64, 3), 90, np.uint8))
        writer.write(np.full((64, 64, 3), 110, np.uint8))
        writer.release()
        capture = cv2.VideoCapture(filename)
        ok, frame = capture.read()
        capture.release()
        assert ok and frame is not None and frame.shape == (64, 64, 3), (
            'OpenCV bundled video decoder failed for ' + extension
        )
    finally:
        os.unlink(filename)
print(json.dumps({
    'python': sys.version.split()[0],
    'executable': str(base),
    'numpy': np.__version__,
    'opencv': cv2.__version__,
    'video': 'AVI/MP4 codecs OK',
}))
`
const env = { ...process.env, PYTHONNOUSERSITE: '1' }
delete env.PYTHONHOME
delete env.PYTHONPATH
delete env.VIRTUAL_ENV
delete env.UV_PROJECT_ENVIRONMENT
// Catch accidental reliance on Python installations in the build machine's
// PATH. Standard Windows system DLLs remain accessible.
const windowsDir = process.env.SystemRoot || 'C:\\Windows'
env.PATH = [runtime, path.join(windowsDir, 'System32'), windowsDir].join(';')
const result = spawnSync(executable, ['-I', '-c', verification], {
  cwd: runtime,
  env,
  encoding: 'utf8',
  timeout: 60_000,
  maxBuffer: 2 * 1024 * 1024,
  windowsHide: true,
})
if (result.error || result.status !== 0) {
  throw new Error([
    'Bundled Python is incomplete or cannot decode video.',
    'Interpreter: ' + executable,
    result.error?.message ?? 'exit status: ' + result.status,
    'stdout: ' + (result.stdout || '').slice(-4_000),
    'stderr: ' + (result.stderr || '').slice(-8_000),
  ].join('\n'))
}
console.log('[verify-runtime] ' + result.stdout.trim())
