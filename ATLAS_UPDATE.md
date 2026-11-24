# Low-Poly Atlas update
Copy these into the repo root (same paths):
- generate.py, atlas.py, template_atlas.html
- atlas_node/atlas_render.mjs, atlas_node/web/fonts/fonts.css
- .github/workflows/kit-daily.yml
Delete (old styles): toon.py scenes.py kitpost.py engine/ .github/workflows/daily.yml .github/workflows/kit-test.yml 1.zip videos/ voice/
Then run kit-daily manually once with skip_upload = true.
