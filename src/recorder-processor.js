class RecorderProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this.buffer = [];
    }

    process(inputs) {
        const input = inputs[0];
        if (input.length > 0) {
            const pcmData = input[0];
            const int16Array = new Int16Array(pcmData.length);
            for (let i = 0; i < pcmData.length; i++) {
                let s = Math.max(-1, Math.min(1, pcmData[i]));
                int16Array[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }
            this.buffer.push(int16Array);

            // z.B. wenn wir ca. 160 ms gesammelt haben, schicken
            if (this.buffer.length >= 20) {
                // Alle gepufferten Arrays zu einem großen zusammenführen
                const totalLength = this.buffer.reduce((sum, arr) => sum + arr.length, 0);
                const combined = new Int16Array(totalLength);
                let offset = 0;
                for (const arr of this.buffer) {
                    combined.set(arr, offset);
                    offset += arr.length;
                }
                this.port.postMessage(combined.buffer);
                this.buffer = [];
            }
        }
        return true;
    }
}

registerProcessor("recorder-processor", RecorderProcessor);
