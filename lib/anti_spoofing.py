import torch
import torchaudio
import numpy as np
import asyncio

from check_audio_file import check_audio_file

device = "cuda" if torch.cuda.is_available() else "cpu"

# Beispiel: Modell wird aus externem Loader importiert
from model_loader import get_model

def load_model():
    model = get_model()
    model.to(device)
    model.eval()
    return model

def resample_audio(audio_chunk):
    audio_np = np.frombuffer(audio_chunk, dtype=np.uint8) - 128
    audio_tensor = torch.from_numpy(audio_np).float()
    resampler = torchaudio.transforms.Resample(orig_freq=8000, new_freq=16000)
    resampled_tensor = resampler(audio_tensor)
    resampled_tensor = resampled_tensor / torch.max(torch.abs(resampled_tensor) + 1e-9)
    return resampled_tensor

async def anti_spoofing_worker(audio_queue: asyncio.Queue, spoof_results_queue: asyncio.Queue, model):
    print("Anti-spoofing worker started.")
    SPOOFING_WINDOW_SIZE_SAMPLES = 16000 * 2  # 2 Sekunden bei 16kHz
    spoofing_buffer = []

    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break

        resampled_chunk = resample_audio(chunk)
        spoofing_buffer.append(resampled_chunk)

        current_buffer_size = sum(c.size(0) for c in spoofing_buffer)
        if current_buffer_size >= SPOOFING_WINDOW_SIZE_SAMPLES:

            print(f"resampled_chunk shape: {resampled_chunk.shape}")
            print(f"buffer elements shapes before cat: {[c.shape for c in spoofing_buffer]}")

            audio_tensor = torch.cat(spoofing_buffer, dim=0)  # concat 1D Tensor

            print(f"audio_tensor shape after cat: {audio_tensor.shape}")

            audio_window = audio_tensor.unsqueeze(0)  # Shape: [1, 32000]
            #audio_window = audio_window.unsqueeze(1)  # Shape: [1, 1, 32000]

            print(f"audio_window shape after unsqueeze: {audio_window.shape}")


            with torch.no_grad():

                check_audio_file(audio_window, sr=16000)

                print("Calculating score")
                print(f"Model device: {next(model.parameters()).device}")
                output = model(audio_window)
                print(f"Model output type: {type(output)}")
                print(f"Model output: {output}")
                if isinstance(output, tuple):
                    print(f"Output is a tuple with {len(output)} elements:")
                    for i, elem in enumerate(output):
                        print(f"Element {i} type: {type(elem)}, value: {elem}, shape: {elem.shape if hasattr(elem, 'shape') else 'N/A'}")
                    logits = output[1]  # Zweites Element enthält Logits [1, 2]
                    print(f"Logits: {logits}")
                    probs = torch.softmax(logits, dim=1)  # Konvertiere zu Wahrscheinlichkeiten
                    print(f"Probabilities: {probs}")
                    score = probs[0, 0].item()  # Wahrscheinlichkeit für Klasse 0 (echt)
                    print(f"Extracted score (probability for class 0): {score}")
                else:
                    score = output.item()
                    print(f"Extracted score (single tensor): {score}")
                await spoof_results_queue.put(score)
            spoofing_buffer = []


    audio_queue.task_done()
    print("Anti-spoofing worker finished.")