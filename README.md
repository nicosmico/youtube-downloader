# Descargar mp3 de YouTube

Esta es una aplicación web que permite descargar archivos de audio en formato mp3 desde videos de YouTube. Simplemente ingresa la URL del video de YouTube y haz clic en el botón de descarga.
Esta aplicación utiliza las siguientes bibliotecas y herramientas:

- pytube3: Para descargar videos de YouTube.
- moviepy: Para convertir videos a formato mp3.
- Flask: Un framework web utilizado para construir la aplicación.

## Instalación

1. Clona este repositorio en tu máquina local.
2. Asegúrate de tener instalado Python 3.10.
3. Instala las dependencias ejecutando los siguientes comandos:

   ```
   pip install -r requirements.txt
   python -m pip install --upgrade pytube
   ```

## Uso

1. Ejecuta la aplicación utilizando el siguiente comando:

   ```
   python .\app\app.py
   ```

2. Abre tu navegador web y accede a `http://localhost:5000`.
3. Ingresa la URL del video de YouTube en el campo de entrada y haz clic en el botón de descarga.
4. El archivo de audio mp3 se descargará en tu dispositivo.
