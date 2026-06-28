#!/bin/bash

# Detener el script si un comando falla
set -e

# --- Variables de Configuración ---
# Directorio de instalación de la aplicación
APP_NAME="youtube-audio-downloader"
INSTALL_DIR="/opt/$APP_NAME"

# Nombre y ubicación del icono
ICON_NAME="youtube-audio-downloader"
ICON_SOURCE_PATH="data/$ICON_NAME.svg"
ICON_INSTALL_PATH="/usr/share/icons/hicolor/scalable/apps"

# Detectar el directorio home del usuario real, incluso con sudo
if [ -n "$SUDO_USER" ]; then
    USER_HOME=$(getent passwd "$SUDO_USER" | cut -d: -f6)
else
    USER_HOME="$HOME"
fi

# Ubicación de los lanzadores de aplicaciones del usuario
DESKTOP_ENTRY_DIR="$USER_HOME/.local/share/applications"
DESKTOP_ENTRY_FILE="$DESKTOP_ENTRY_DIR/$APP_NAME.desktop"

# --- Comprobaciones Previas ---
echo "Iniciando la instalación de YouTube Audio Downloader..."

# 1. Comprobar si se ejecuta como root (necesario para /opt y /usr/share)
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: Este script debe ser ejecutado con privilegios de superusuario (sudo)." >&2
  exit 1
fi

# 2. Comprobar que los archivos necesarios existen
if [ ! -d "youtubeaudiodownloader" ] || [ ! -f "youtube_audio_downloader.py" ] || [ ! -f "youtube-audio-downloader.desktop.template" ]; then
    echo "Error: Faltan archivos. Asegúrate de ejecutar este script desde la raíz del proyecto." >&2
    exit 1
fi

# --- Instalación ---

# 1. Crear el directorio de instalación y copiar los archivos de la aplicación
echo "Instalando archivos de la aplicación en $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
cp -r youtubeaudiodownloader "$INSTALL_DIR/"
cp youtube_audio_downloader.py "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/youtube_audio_downloader.py" # Asegurarse de que sea ejecutable

# 2. Instalar el icono
if [ -f "$ICON_SOURCE_PATH" ]; then
    echo "Instalando icono en $ICON_INSTALL_PATH..."
    mkdir -p "$ICON_INSTALL_PATH"
    cp "$ICON_SOURCE_PATH" "$ICON_INSTALL_PATH/"
    # Actualizar la caché de iconos
    gtk-update-icon-cache -f -t "$ICON_INSTALL_PATH" || echo "Advertencia: no se pudo actualizar la caché de iconos."
else
    echo "Advertencia: no se encontró el archivo del icono en $ICON_SOURCE_PATH. Se usará un icono genérico."
fi

# 3. Crear el lanzador .desktop para el usuario que ejecutó sudo
echo "Creando el lanzador de la aplicación en $DESKTOP_ENTRY_DIR..."
mkdir -p "$DESKTOP_ENTRY_DIR"

# Reemplazar los marcadores de posición en la plantilla y crear el archivo final
sed -e "s|__INSTALL_PATH__|$INSTALL_DIR|g" \
    -e "s|__ICON_NAME__|$ICON_INSTALL_PATH/$ICON_NAME.svg|g" \
    youtube-audio-downloader.desktop.template > "$DESKTOP_ENTRY_FILE"

# Ajustar permisos del lanzador
chmod +x "$DESKTOP_ENTRY_FILE"

echo ""
echo "✅ ¡Instalación completada!"
echo "Encontrarás 'YouTube Audio Downloader' en tu menú de aplicaciones."