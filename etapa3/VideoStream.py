import cv2

class VideoStream:
    def __init__(self, filename):
        self.filename = filename
        self.cap = cv2.VideoCapture(filename)  # Usar OpenCV para abrir o vídeo
        if not self.cap.isOpened():
            raise IOError(f"Não foi possível abrir o arquivo de vídeo {filename}")
        self.frame_num = 0

    def nextFrame(self):
        """Retorna o próximo quadro do vídeo como um array de bytes."""
        success, frame = self.cap.read()  # Lê o próximo quadro
        if not success:
            return None  # Retorna None se não houver mais quadros

        self.frame_num += 1
        _, encoded_frame = cv2.imencode('.jpg', frame)  # Codifica o quadro em JPEG para envio
        return encoded_frame.tobytes()  # Converte para bytes

    def frameNbr(self):
        """Retorna o número do quadro atual."""
        return self.frame_num
    
    def release(self):
        """Libera o recurso do vídeo."""
        self.cap.release()

	