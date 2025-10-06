FROM python:3.11-slim

# Instalar git
RUN apt-get update && apt-get install -y git

# Instalar Poetry
RUN pip install --no-cache-dir poetry

# Verificar git
RUN git --version

# Usuario jenkins con el que se realizarán todas las acciones en el contenedor
RUN groupadd -g 1001 jenkins && \
    useradd -u 1001 -g jenkins -m -s /bin/bash jenkins && \
    mkdir /app && \
    chown -R jenkins:jenkins /app && \
    chmod 774 /app

# Establecer el directorio de trabajo en /app
WORKDIR /app

# Copiar scripts al contenedor y dar permisos al usuario jenkins
COPY --chown=jenkins:jenkins --chmod=744 scripts /scripts

# Establecer el usuario jenkins como usuario por defecto
USER jenkins

# Variables de entorno
ENV JOB_ACTION="bump"
ENV GITLAB_CREDENTIAL_USER=""
ENV GITLAB_CREDENTIAL_PASSWORD=""

# Ejecutar el script node.sh como punto de entrada y asegurar que los errores se propaguen
ENTRYPOINT ["/bin/bash", "-c", "set -e; /scripts/bump.sh; exit $?"] 