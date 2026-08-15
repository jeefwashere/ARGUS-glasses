class Pcm16Downsampler extends AudioWorkletProcessor {
  constructor(options) {
    super();

    const settings = options.processorOptions || {};
    this.targetSampleRate = settings.targetSampleRate || 16000;
    this.chunkSamples = settings.chunkSamples || 320;
    this.sourceSamplesPerTarget = sampleRate / this.targetSampleRate;
    this.sourceBuffer = [];
    this.sourcePosition = 0;
    this.outputBuffer = [];
  }

  process(inputs, outputs) {
    const channel = inputs[0] && inputs[0][0];
    const output = outputs[0] && outputs[0][0];

    if (output) {
      output.fill(0);
    }

    if (!channel || channel.length === 0) {
      return true;
    }

    for (let index = 0; index < channel.length; index += 1) {
      this.sourceBuffer.push(channel[index]);
    }

    this.downsampleAvailableAudio();
    return true;
  }

  downsampleAvailableAudio() {
    while (
      this.sourcePosition + this.sourceSamplesPerTarget <=
      this.sourceBuffer.length
    ) {
      const start = this.sourcePosition;
      const end = start + this.sourceSamplesPerTarget;
      const firstIndex = Math.floor(start);
      const lastIndex = Math.min(Math.ceil(end), this.sourceBuffer.length);
      let weightedSum = 0;
      let totalWeight = 0;

      for (let index = firstIndex; index < lastIndex; index += 1) {
        const overlapStart = Math.max(start, index);
        const overlapEnd = Math.min(end, index + 1);
        const weight = Math.max(0, overlapEnd - overlapStart);

        weightedSum += this.sourceBuffer[index] * weight;
        totalWeight += weight;
      }

      const sample = totalWeight > 0 ? weightedSum / totalWeight : 0;
      this.outputBuffer.push(this.floatToPcm16(sample));
      this.sourcePosition = end;

      if (this.outputBuffer.length >= this.chunkSamples) {
        this.emitChunk();
      }
    }

    const removableSamples = Math.floor(this.sourcePosition);
    if (removableSamples > 0) {
      this.sourceBuffer.splice(0, removableSamples);
      this.sourcePosition -= removableSamples;
    }
  }

  emitChunk() {
    const chunk = new Int16Array(this.outputBuffer.splice(0, this.chunkSamples));
    this.port.postMessage(chunk.buffer, [chunk.buffer]);
  }

  floatToPcm16(value) {
    const clamped = Math.max(-1, Math.min(1, value));
    return clamped < 0
      ? Math.round(clamped * 0x8000)
      : Math.round(clamped * 0x7fff);
  }
}

registerProcessor("pcm16-downsampler", Pcm16Downsampler);
