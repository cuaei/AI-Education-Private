FROM mcr.microsoft.com/playwright/python:v1.51.0-noble
USER root
RUN pip install --no-cache-dir fastapi==0.115.12 uvicorn==0.34.0 httpx==0.28.1 playwright==1.51.0
# Playwright's pinned wheel contains a Linux Node runtime. Use it for fixed frontend builds.
RUN python -c "import pathlib,playwright,shutil; shutil.copyfile(pathlib.Path(playwright.__file__).parent/'driver'/'node','/usr/local/bin/node')" && chmod +x /usr/local/bin/node
RUN python -c "import urllib.request,tarfile; urllib.request.urlretrieve('https://registry.npmjs.org/npm/-/npm-10.9.2.tgz','/tmp/npm.tgz'); tarfile.open('/tmp/npm.tgz').extractall('/opt/npm',filter='data')" && ln -s /opt/npm/package/bin/npm-cli.js /usr/local/bin/npm
WORKDIR /opt/student-deps
COPY reference/frontend/package.json package.json
RUN npm install --ignore-scripts --no-audit --no-fund
COPY start.sh /opt/start.sh
COPY empty-vite.config.mjs /opt/empty-vite.config.mjs
RUN chmod +x /opt/start.sh && useradd --uid 10001 --create-home learner
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
WORKDIR /tmp
CMD ["/opt/start.sh"]
