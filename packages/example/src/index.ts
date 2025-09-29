import { TickEngine, ILoopState } from "@rasl/core/tick/engine";
import { TimeoutTickDriver } from "@rasl/core/tick/timeout";

const engine = new TickEngine(new TimeoutTickDriver({ hz: 20 }));
engine.add((state: ILoopState) => {
	console.log("tick", state);
});

console.log("start", engine);
engine.start();
