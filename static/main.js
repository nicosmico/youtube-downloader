document.addEventListener('DOMContentLoaded', () => {
    const downloadButton = document.getElementById('download-button');
    const youtubeLinkInput = document.getElementById('youtube-link');
    const statusMessage = document.getElementById('status-message');

    downloadButton.addEventListener('click', async () => {
        const youtubeLink = youtubeLinkInput.value.trim();

        if (!youtubeLink) {
            statusMessage.textContent = 'Por favor ingresa una URL de YouTube.';
            return;
        }

        const isValidUrl = isValidYoutubeUrl(youtubeLink);

        if (!isValidUrl) {
            statusMessage.textContent = 'URL de YouTube inválida.';
            return;
        }

        const downloadUrl = `/watch?v=${encodeURIComponent(youtubeLink)}`;

        statusMessage.textContent = 'Descargando...';
        downloadButton.disabled = true;

        try {
            const response = await fetch(downloadUrl, { method: 'GET' });

            if (response.ok) {
                const disposition = response.headers.get('content-disposition');
                const filenameRegex = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/;
                const matches = filenameRegex.exec(disposition);
                const filename = matches != null && matches[1] ? matches[1].replace(/['"]/g, '') : 'descarga.mp3';

                const blob = await response.blob();
                const url = URL.createObjectURL(blob);
                const link = document.createElement('a');
                link.href = url;
                link.download = filename;
                link.click();
                URL.revokeObjectURL(url);
                statusMessage.textContent = 'Descarga completada.';
            } else {
                throw new Error('Se produjo un error durante la descarga.');
            }
        } catch (error) {
            console.error(error);
            statusMessage.textContent = 'Se produjo un error durante la descarga.';
        }

        downloadButton.disabled = false;
    });

    function isValidYoutubeUrl(url) {
        try {
            new URL(url);
            return true;
        } catch (error) {
            return false;
        }
    }
});
