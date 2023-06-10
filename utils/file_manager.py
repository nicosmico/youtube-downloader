import os

class FileManager:
    @staticmethod
    def delete_file(file_path: str) -> bool:
        """
        Delete a file from the file system.
        Returns True if the file is successfully deleted, False otherwise.
        """
        try:
            os.remove(file_path)
            print(f'[File manager] Deleted file: {file_path}')
            return True
        except Exception as e:
            print(f'[File manager] Error deleting file: {file_path}')
            print(f'[File manager] Error: {str(e)}')
            return False
