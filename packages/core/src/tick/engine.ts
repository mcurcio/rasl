export interface ITickFunction {
	(state: ITickState): void;
}

export interface ITickState {
	/**
	 * Absolute time in milliseconds
	 */
	time: number;

	/**
	 * The milliseconds since the last tick
	 */
	delta: number;
}

export interface ITickEngine {
	start(): void
	stop(): void

	add(fn: ITickFunction): void
	remove(fn: ITickFunction): void
}

export interface IPendingTick {}

export interface ITickDriver {
	/**
	 * Request a new ticket
	 * @param fn The function to call on the next tick
	 * @param state The previous state, if this is a continuation
	 */
	request(fn: ITickFunction, state?: ITickState): IPendingTick;

	/**
	 * Cancel a pending tick
	 * @param tick The tick to cancel
	 */
	cancel(tick: IPendingTick): void;
}

export class TickEngine implements ITickEngine {
	private running = false;
	private pending: IPendingTick | null = null;
	private operations: ITickFunction[] = [];

	constructor(private readonly driver: ITickDriver) {}

	public start(): void {
		this.running = true;
		this.pending = this.driver.request(this.tick.bind(this));
	}

	public stop(): void {
		this.running = false;
		if (this.pending) {
			this.driver.cancel(this.pending);
			this.pending = null;
		}
	}

	private tick(state: ITickState): void {
		if (this.running) {
			for (const operation of this.operations) {
				try {
					operation(state);
				} catch (e) {
					console.error(e);
				}
			}

			this.pending = this.driver.request(this.tick.bind(this), state);
		}
	}

	public add(fn: ITickFunction): void {
		this.operations.push(fn);
	}

	public remove(fn: ITickFunction): void {
		const index = this.operations.indexOf(fn);
		if (index !== -1) {
			this.operations.splice(index, 1);
		}
	}
}
