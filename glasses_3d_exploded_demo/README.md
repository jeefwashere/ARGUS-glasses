# ARGUS exploded glasses demo

This directory is a self contained static copy of the 3D glasses scroll showcase. It includes the local Three.js module, GLTF loader utilities, GSAP, ScrollTrigger, and the GLB model. The voice assistant page and its application scripts are not included.

Run it from this directory with:

```bash
python3 -m http.server 8080
```

Then open <http://127.0.0.1:8080/> in a browser. A local HTTP server is required so that the module import map and GLB fetch work correctly.
