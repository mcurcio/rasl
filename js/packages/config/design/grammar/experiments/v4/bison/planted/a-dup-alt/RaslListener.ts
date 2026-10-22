// Generated from Rasl.g4 by ANTLR 4.13.2

import {ParseTreeListener} from "antlr4";


import { DocumentContext } from "./RaslParser.js";
import { StatementsContext } from "./RaslParser.js";
import { FillerContext } from "./RaslParser.js";
import { DirectiveContext } from "./RaslParser.js";
import { LastDirectiveContext } from "./RaslParser.js";
import { HeaderContext } from "./RaslParser.js";
import { RestContext } from "./RaslParser.js";
import { GapContext } from "./RaslParser.js";
import { SeparatorContext } from "./RaslParser.js";
import { BlockContext } from "./RaslParser.js";
import { ValueContext } from "./RaslParser.js";
import { SlicedWordContext } from "./RaslParser.js";
import { BoundsContext } from "./RaslParser.js";
import { ListContext } from "./RaslParser.js";
import { ItemsContext } from "./RaslParser.js";
import { ListGapContext } from "./RaslParser.js";


/**
 * This interface defines a complete listener for a parse tree produced by
 * `RaslParser`.
 */
export default class RaslListener extends ParseTreeListener {
	/**
	 * Enter a parse tree produced by `RaslParser.document`.
	 * @param ctx the parse tree
	 */
	enterDocument?: (ctx: DocumentContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.document`.
	 * @param ctx the parse tree
	 */
	exitDocument?: (ctx: DocumentContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.statements`.
	 * @param ctx the parse tree
	 */
	enterStatements?: (ctx: StatementsContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.statements`.
	 * @param ctx the parse tree
	 */
	exitStatements?: (ctx: StatementsContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.filler`.
	 * @param ctx the parse tree
	 */
	enterFiller?: (ctx: FillerContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.filler`.
	 * @param ctx the parse tree
	 */
	exitFiller?: (ctx: FillerContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.directive`.
	 * @param ctx the parse tree
	 */
	enterDirective?: (ctx: DirectiveContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.directive`.
	 * @param ctx the parse tree
	 */
	exitDirective?: (ctx: DirectiveContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.lastDirective`.
	 * @param ctx the parse tree
	 */
	enterLastDirective?: (ctx: LastDirectiveContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.lastDirective`.
	 * @param ctx the parse tree
	 */
	exitLastDirective?: (ctx: LastDirectiveContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.header`.
	 * @param ctx the parse tree
	 */
	enterHeader?: (ctx: HeaderContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.header`.
	 * @param ctx the parse tree
	 */
	exitHeader?: (ctx: HeaderContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.rest`.
	 * @param ctx the parse tree
	 */
	enterRest?: (ctx: RestContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.rest`.
	 * @param ctx the parse tree
	 */
	exitRest?: (ctx: RestContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.gap`.
	 * @param ctx the parse tree
	 */
	enterGap?: (ctx: GapContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.gap`.
	 * @param ctx the parse tree
	 */
	exitGap?: (ctx: GapContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.separator`.
	 * @param ctx the parse tree
	 */
	enterSeparator?: (ctx: SeparatorContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.separator`.
	 * @param ctx the parse tree
	 */
	exitSeparator?: (ctx: SeparatorContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.block`.
	 * @param ctx the parse tree
	 */
	enterBlock?: (ctx: BlockContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.block`.
	 * @param ctx the parse tree
	 */
	exitBlock?: (ctx: BlockContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.value`.
	 * @param ctx the parse tree
	 */
	enterValue?: (ctx: ValueContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.value`.
	 * @param ctx the parse tree
	 */
	exitValue?: (ctx: ValueContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.slicedWord`.
	 * @param ctx the parse tree
	 */
	enterSlicedWord?: (ctx: SlicedWordContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.slicedWord`.
	 * @param ctx the parse tree
	 */
	exitSlicedWord?: (ctx: SlicedWordContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.bounds`.
	 * @param ctx the parse tree
	 */
	enterBounds?: (ctx: BoundsContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.bounds`.
	 * @param ctx the parse tree
	 */
	exitBounds?: (ctx: BoundsContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.list`.
	 * @param ctx the parse tree
	 */
	enterList?: (ctx: ListContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.list`.
	 * @param ctx the parse tree
	 */
	exitList?: (ctx: ListContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.items`.
	 * @param ctx the parse tree
	 */
	enterItems?: (ctx: ItemsContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.items`.
	 * @param ctx the parse tree
	 */
	exitItems?: (ctx: ItemsContext) => void;
	/**
	 * Enter a parse tree produced by `RaslParser.listGap`.
	 * @param ctx the parse tree
	 */
	enterListGap?: (ctx: ListGapContext) => void;
	/**
	 * Exit a parse tree produced by `RaslParser.listGap`.
	 * @param ctx the parse tree
	 */
	exitListGap?: (ctx: ListGapContext) => void;
}

