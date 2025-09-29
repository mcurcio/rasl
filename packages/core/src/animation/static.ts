import { IAnimation } from "./animation";

export class StaticAnimation implements IAnimation {
	constructor(private readonly data: number[]) {}

	public get duration(): number {
		return 0;
	}

	public get channels(): number {
		return this.data.length;
	}

	public values(): number[] {
		return this.data;
	}
}