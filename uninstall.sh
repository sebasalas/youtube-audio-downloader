#!/bin/bash

# Detener el script si un comando falla
set -e

# --- Variables de Configuración (deben ser las mismas que en install.sh) ---
APP_NAME="youtube-audio-downloader"
INSTALL_DIR="/opt/$APP_NAME"
ICON_NAME="youtube-audio-downloader"
ICON_INSTALL_PATH="/usr/share/icons/hicolor/scalable/apps/$ICON_NAME.svg"
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
echo "Iniciando la desinstalación de YouTube Audio Downloader..."

# 1. Comprobar si se ejecuta como root
if [ "$(id -u)" -ne 0 ]; then
  echo "Error: Este script debe ser ejecutado con privilegios de superusuario (sudo)." >&2
  exit 1
fi

# --- Desinstalación ---

# 1. Eliminar los archivos de la aplicación
if [ -d "$INSTALL_DIR" ]; then
    echo "Eliminando directorio de la aplicación: $INSTALL_DIR..."
    rm -rf "$INSTALL_DIR"
else
    echo "El directorio de la aplicación no existe, omitiendo."
fi

# 2. Eliminar el icono
if [ -f "$ICON_INSTALL_PATH" ]; then
    echo "Eliminando icono: $ICON_INSTALL_PATH..."
    rm -f "$ICON_INSTALL_PATH"
    # Actualizar la caché de iconos
    gtk-update-icon-cache -f -t "$(dirname "$ICON_INSTALL_PATH")" || echo "Advertencia: no se pudo actualizar la caché de iconos."
else
    echo "El icono no existe, omitiendo."
fi

# 3. Eliminar el lanzador .desktop
if [ -f "$DESKTOP_ENTRY_FILE" ]; then
    echo "Eliminando lanzador de la aplicación: $DESKTOP_ENTRY_FILE..."
    rm -f "$DESKTOP_ENTRY_FILE"
else
    echo "El lanzador de la aplicación no existe, omitiendo."
fi

echo ""
echo "✅ ¡Desinstalación completada!"