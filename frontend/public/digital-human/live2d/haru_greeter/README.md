# Haru Greeter Live2D Runtime

This directory is based on the runtime export copied from the local
`haru_greeter_ja/runtime/` sample package. The deployed `pose3.json` orders
the A arms before the B arms so its initial pose matches the supplied idle
motion. The deployed `model3.json` also gives the idle motion a 0.01-second
fade-in because the renderer's 0.5-second default blends Haru's mutually
exclusive arm variants into a visible ghost. The source package remains
unchanged.

- Model: Haru receptionist version PRO (`haru_greeter_t05`)
- Creator and copyright owner: Live2D Inc.
- Source: Live2D official sample data
- Terms: <https://www.live2d.com/en/learn/sample/model-terms/>

The application exposes this model through the compatibility avatar ID
`mao_pro`. The original Mao Pro runtime remains in the adjacent `mao_pro/`
directory so the visual replacement can be rolled back without restoring
deleted assets.

Review the official sample-data terms before distributing the application.
