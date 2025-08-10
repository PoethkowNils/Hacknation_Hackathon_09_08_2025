import librosa
import librosa.display
import matplotlib.pyplot as plt
import numpy as np

def check_audio_file(audio_input, sr=16000, plot=True):
    """
    Prüft Audioqualität und zeigt Spektrogramm.

    audio_input:
        - Entweder Dateipfad (str) ODER
        - 1D numpy array mit Audiodaten

    sr: Samplingrate, falls audio_input ein Array ist.
    """
    if isinstance(audio_input, str):
        audio, sr = librosa.load(audio_input, sr=None)
        filename = audio_input
    else:
        # Audioarray: evtl Tensor -> numpy
        if hasattr(audio_input, "numpy"):
            audio = audio_input.squeeze().cpu().numpy()
        else:
            audio = np.array(audio_input).squeeze()
        filename = "<raw audio array>"

    print(f"Audioquelle: {filename}")
    print(f"Samplingrate: {sr} Hz")
    print(f"Dauer: {len(audio)/sr:.2f} Sekunden")
    print(f"Maximaler Wert: {max(audio):.3f}, Minimaler Wert: {min(audio):.3f}")

    if plot:
        S = librosa.feature.melspectrogram(y=audio, sr=sr, n_mels=40)
        log_S = librosa.power_to_db(S, ref=np.max)
        plt.figure(figsize=(10, 4))
        librosa.display.specshow(log_S, sr=sr, x_axis='time', y_axis='mel')
        plt.colorbar(format='%+02.0f dB')
        plt.title('Log-Mel-Spectrogram')
        plt.tight_layout()
        plt.show()
