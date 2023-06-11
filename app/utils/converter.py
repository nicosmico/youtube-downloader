from moviepy.editor import AudioFileClip

class Converter:
    @staticmethod
    def convert_to_mp3(file_path: str) -> str | None:
        """
        Convert file in file_path to .mp3
        """
        try:
            file_name = file_path.split('/')[-1]
            print(f'[Converter] Converting {file_name} to mp3...')

            file = AudioFileClip(file_path)

            output_file = file_path.split('.')[0] + '.mp3'
            file.write_audiofile(output_file)
            file.close()
            print('[Converter] Conversion completed.')
            return output_file

        except Exception as e:
            print(f'[Converter] Error converting to mp3: {file_path}')
            print(f'[Converter] Error: {str(e)}')
            return None
