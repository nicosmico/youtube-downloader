from pytube import YouTube
import os

class Downloader:
    @staticmethod
    def download_by_link(link: str, output_path: str | None = None) -> str | None:
        """
        Download youtube video by link
        """

        current_path = os.getcwd()
        output_path = output_path or os.path.join(current_path, 'downloads')

        try:
            yt = YouTube(link)
            print('[Downloader] Video name: ', yt.title)
            print('[Downloader] Video channel: ', yt.author)

            # Get best stream by abr
            # streams = yt.streams.order_by('abr').desc()
            streams = yt.streams.filter(only_audio=True).order_by('abr').desc()
            if not streams or len(streams) == 0:
                print('[Downloader] Streams not found.')
                return None

            # Download
            stream = streams[0]
            print(f'[Downloader] Downloading {yt.title}...')
            # print('[Downloader] Stream: ', stream)
            file_path = stream.download(output_path=output_path)
            print('[Downloader] Download completed.')
            return file_path

        except Exception as e:
            print(f'[Downloader] Error downloading file: {link}')
            print(f'[Downloader] Error: {str(e)}')
            return None
