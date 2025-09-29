export abstract class Animation {
	protected children: Animation[] = [];

	protected durationMs?: number;
	protected timeRatio: number = 1;
	protected channelCount: number = 0;

	private startTime: number = 0;
	private endTime?: number;
	private currentTime: number = 0;

	constructor(durationMs?: number) {
		this.durationMs = durationMs;
		this.endTime = durationMs;
	}

	protected addChildren(...animations: Animation[]): void {
		this.children.push(...animations);
	}

	protected removeChildren(...animations: Animation[]): void {
		this.children = this.children.filter(a => !animations.includes(a));
	}

	public get channels(): number {
		return this.channelCount;
	}

	public get finished(): boolean {
		return true;
	}

	public abstract values(ms: number): number[] {
		return this.data;
	}
}

export class WarpAnimation extends Animation {
	constructor(public readonly duration: number, private readonly animation: Animation) {
		super();
		this.timeRatio = 0.5;
	}

	public get finished(): boolean {
		return this.time >= this.duration;
	}

	public values(ms: number): number[] {
		this.time = ms;
		return this.animation.values(ms);
	}
}