import { IAnimation } from "./animation";

export class EaseAnimation implements IAnimation {
	constructor(public readonly duration: number, private readonly start: IAnimation, private readonly end: IAnimation) {
		if (start.channels !== end.channels) {
			throw new Error("Start and end animations must have the same number of channels");
		}
	}

	public get channels(): number {
		return this.start.channels;
	}

	public values(ms: number): number[] {
		const t = Math.min(ms / this.duration, 1);
		const v = this.ease(t);
		return this.data.map(d => d * v);
	}
}