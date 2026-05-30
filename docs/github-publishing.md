# Publishing To GitHub

This folder is ready to become the root of a GitHub repository.

## Create The Repository

1. Sign in to GitHub.
2. Click **New repository**.
3. Name it:

```text
home-assistant-legrand-xerus
```

4. Keep it public if you want other people to install it through HACS.
5. Do not add a README, license, or `.gitignore` in GitHub because they already exist here.
6. Create the empty repository.

## Push From This Folder

From the `home-assistant-legrand-xerus` folder:

```bash
git init
git add .
git commit -m "Initial beta POC release"
git branch -M main
git remote add origin https://github.com/<your-user>/home-assistant-legrand-xerus.git
git push -u origin main
```

## Add A Release Tag

HACS can install from the default branch as a custom repository, but tagged releases are cleaner.

```bash
git tag v0.4.7
git push origin v0.4.7
```

## HACS Custom Repository URL

Give users the GitHub repo URL:

```text
https://github.com/<your-user>/home-assistant-legrand-xerus
```

They add it in HACS as category **Integration**.
