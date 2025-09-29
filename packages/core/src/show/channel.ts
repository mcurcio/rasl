export interface IChannelConfig {
	/**
	 * The name of the channel.
	 */
	readonly name?: string;

	/**
	 * The range of the channel, [low, high].
	 * @default [0, 1]
	 */
	readonly range?: [number, number];

	/**
	 * Does the range of the channel wrap around?
	 * @default false
	 */
	readonly rollover?: boolean;
}

export class ShowChannel {
	public readonly name?: string;
	public readonly range: [number, number] = [0, 1];
	public readonly rollover: boolean = false;

	constructor(private readonly config: IChannelConfig) {
		this.name = config.name;
		this.range = config.range ?? this.range;
		this.rollover = config.rollover ?? this.rollover;
	}
}