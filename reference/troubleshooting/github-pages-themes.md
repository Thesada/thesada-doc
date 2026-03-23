---
title: GitHub Pages with Third-Party Jekyll Themes
parent: Troubleshooting
nav_order: 5
description: "Fix GitHub Pages build failures with third-party Jekyll themes using a GitHub Actions workflow."
---

# GitHub Pages Not Building with a Third-Party Jekyll Theme

## Symptom

You configure a third-party Jekyll theme (e.g. `just-the-docs`) using
`remote_theme` in `_config.yml`. The site builds locally with
`bundle exec jekyll serve` but GitHub Pages shows a build failure
or renders without the theme.

## Cause

GitHub Pages' default build process only supports a limited set of
whitelisted Jekyll themes. Third-party themes like `just-the-docs` are
not in this list. The `remote_theme` plugin works locally but the
default GitHub Pages builder does not execute it.

## Fix

Use a GitHub Actions workflow instead of the default GitHub Pages builder.

### 1. Create the workflow file

Create `.github/workflows/pages.yml` in your repo:

```yaml
name: Deploy Jekyll site to Pages

on:
  push:
    branches: ["main"]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Ruby
        uses: ruby/setup-ruby@v1
        with:
          ruby-version: '3.3'
          bundler-cache: true
      - name: Setup Pages
        uses: actions/configure-pages@v5
      - name: Build with Jekyll
        run: bundle exec jekyll build --baseurl "${{ steps.pages.outputs.base_path }}"
        env:
          JEKYLL_ENV: production
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3

  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    needs: build
    steps:
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

### 2. Configure GitHub Pages to use Actions

In the repo settings: Settings > Pages > Build and deployment > Source:
select **GitHub Actions** (not "Deploy from a branch").

### 3. Ensure Gemfile includes the theme

```ruby
source "https://rubygems.org"

gem "just-the-docs"
gem "jekyll-seo-tag"
```

### 4. Use theme (not remote_theme) in _config.yml

When using Actions with a Gemfile, set:

```yaml
theme: just-the-docs
```

The `remote_theme` directive is only needed when relying on the default
GitHub Pages builder. With Actions + Gemfile, `theme` is sufficient and
more reliable.

### 5. Push and verify

Push the workflow file. Check the Actions tab for the build. Once
successful, the site deploys to your configured domain.

## Notes

- The Actions workflow has full Ruby/Bundler support, so any gem-based
  theme works.
- Build times are typically 30-60 seconds for small Jekyll sites.
- If the build fails, check the Actions log for missing gems or
  config errors.
