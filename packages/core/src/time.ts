export interface ITimeSource {
	/**
	 * Get the current execution time in milliseconds
	 */
	now(): number;
}

export class PerformanceTimeSource implements ITimeSource {
	public now(): number {
		return performance.now();
	}
}