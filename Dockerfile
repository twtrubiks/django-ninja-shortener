FROM python:3.13-slim

ARG NODE_MAJOR=22

# The installer requires curl (and certificates) to download the release archive
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install nodejs -y \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean

LABEL maintainer twtrubiks
ENV PYTHONUNBUFFERED 1

RUN mkdir /ninja_shortener
WORKDIR /ninja_shortener
COPY . /ninja_shortener/

# Download the latest installer
ADD https://astral.sh/uv/install.sh /uv-installer.sh

# Run the installer then remove it
RUN sh /uv-installer.sh && rm /uv-installer.sh

# Ensure the installed binary is on the `PATH`
ENV PATH="/root/.local/bin/:$PATH"

# Use uv to install packages
RUN uv pip install --no-cache --system -r requirements.txt

# 預先建置 Tailwind CSS，讓生產映像自帶靜態資產（開機由 collectstatic 收集）。
# 開發環境以 volume 掛載原始碼，會由 tailwind 服務即時重建覆蓋，不受此層影響。
RUN python manage.py tailwind install && python manage.py tailwind build

# for entry point
RUN chmod +x /ninja_shortener/entrypoint.sh

# 設定 entrypoint
ENTRYPOINT ["/ninja_shortener/entrypoint.sh"]