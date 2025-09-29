import { ITimeSource } from "../time";
import { ITickFunction, ITickState, IPendingTick, ITickDriver } from "./engine";

export interface ITimeoutTickOps {
	hz: number;
	timer?: ITimeSource;
}

export class TimeoutTickDriver implements ITickDriver {
	private readonly msDelay: number;
	private readonly timer: ITimeSource;

	constructor(private readonly opts: ITimeoutTickOps) {
		this.msDelay = 1000 / opts.hz;
		this.timer = opts.timer ?? performance;
	}

	public request(fn: ITickFunction, state?: ITickState): NodeJS.Timeout {
		const delay = state ? Math.max(0, state.time + this.msDelay - this.timer.now()) : this.msDelay;

		return setTimeout(() => {
			const now = this.timer.now();
			fn({
				time: now,
				delta: now - (state?.time ?? now)
			});
		}, delay);
	}

	public cancel(tick: NodeJS.Timeout): void {
		clearTimeout(tick);
	}
}
