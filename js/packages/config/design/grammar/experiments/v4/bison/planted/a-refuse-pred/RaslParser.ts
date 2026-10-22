// Generated from Rasl.g4 by ANTLR 4.13.2
// noinspection ES6UnusedImports,JSUnusedGlobalSymbols,JSUnusedLocalSymbols

import {
	ATN,
	ATNDeserializer, DecisionState, DFA, FailedPredicateException,
	RecognitionException, NoViableAltException, BailErrorStrategy,
	Parser, ParserATNSimulator,
	RuleContext, ParserRuleContext, PredictionMode, PredictionContextCache,
	TerminalNode, RuleNode,
	Token, TokenStream,
	Interval, IntervalSet
} from 'antlr4';
import RaslListener from "./RaslListener.js";
// for running tests with parameters, TODO: discuss strategy for typed parameters in CI
// eslint-disable-next-line no-unused-vars
type int = number;

export default class RaslParser extends Parser {
	public static readonly BOM = 1;
	public static readonly SPACE = 2;
	public static readonly NEWLINE = 3;
	public static readonly COMMENT = 4;
	public static readonly WORD = 5;
	public static readonly STRING = 6;
	public static readonly LBRACE = 7;
	public static readonly RBRACE = 8;
	public static readonly LBRACK = 9;
	public static readonly RBRACK = 10;
	public static readonly SEMI = 11;
	public static readonly COMMA = 12;
	public static readonly COLON = 13;
	public static readonly UNTERMINATED_STRING = 14;
	public static readonly BAD_CHAR = 15;
	public static override readonly EOF = Token.EOF;
	public static readonly RULE_document = 0;
	public static readonly RULE_statements = 1;
	public static readonly RULE_filler = 2;
	public static readonly RULE_directive = 3;
	public static readonly RULE_lastDirective = 4;
	public static readonly RULE_header = 5;
	public static readonly RULE_rest = 6;
	public static readonly RULE_gap = 7;
	public static readonly RULE_separator = 8;
	public static readonly RULE_block = 9;
	public static readonly RULE_value = 10;
	public static readonly RULE_slicedWord = 11;
	public static readonly RULE_bounds = 12;
	public static readonly RULE_list = 13;
	public static readonly RULE_items = 14;
	public static readonly RULE_listGap = 15;
	public static readonly literalNames: (string | null)[] = [ null, "'\\uFEFF'", 
                                                            null, null, 
                                                            null, null, 
                                                            null, "'{'", 
                                                            "'}'", "'['", 
                                                            "']'", "';'", 
                                                            "','", "':'" ];
	public static readonly symbolicNames: (string | null)[] = [ null, "BOM", 
                                                             "SPACE", "NEWLINE", 
                                                             "COMMENT", 
                                                             "WORD", "STRING", 
                                                             "LBRACE", "RBRACE", 
                                                             "LBRACK", "RBRACK", 
                                                             "SEMI", "COMMA", 
                                                             "COLON", "UNTERMINATED_STRING", 
                                                             "BAD_CHAR" ];
	// tslint:disable:no-trailing-whitespace
	public static readonly ruleNames: string[] = [
		"document", "statements", "filler", "directive", "lastDirective", "header", 
		"rest", "gap", "separator", "block", "value", "slicedWord", "bounds", 
		"list", "items", "listGap",
	];
	public get grammarFileName(): string { return "Rasl.g4"; }
	public get literalNames(): (string | null)[] { return RaslParser.literalNames; }
	public get symbolicNames(): (string | null)[] { return RaslParser.symbolicNames; }
	public get ruleNames(): string[] { return RaslParser.ruleNames; }
	public get serializedATN(): number[] { return RaslParser._serializedATN; }

	protected createFailedPredicateException(predicate?: string, message?: string): FailedPredicateException {
		return new FailedPredicateException(this, predicate, message);
	}

	constructor(input: TokenStream) {
		super(input);
		this._interp = new ParserATNSimulator(this, RaslParser._ATN, RaslParser.DecisionsToDFA, new PredictionContextCache());
	}
	// @RuleVersion(0)
	public document(): DocumentContext {
		let localctx: DocumentContext = new DocumentContext(this, this._ctx, this.state);
		this.enterRule(localctx, 0, RaslParser.RULE_document);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 33;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===1) {
				{
				this.state = 32;
				this.match(RaslParser.BOM);
				}
			}

			this.state = 35;
			this.statements();
			this.state = 36;
			this.match(RaslParser.EOF);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public statements(): StatementsContext {
		let localctx: StatementsContext = new StatementsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 2, RaslParser.RULE_statements);
		let _la: number;
		try {
			let _alt: number;
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 41;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 2076) !== 0)) {
				{
				{
				this.state = 38;
				this.filler();
				}
				}
				this.state = 43;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			}
			this.state = 53;
			this._errHandler.sync(this);
			_alt = this._interp.adaptivePredict(this._input, 3, this._ctx);
			while (_alt !== 2 && _alt !== ATN.INVALID_ALT_NUMBER) {
				if (_alt === 1) {
					{
					{
					this.state = 44;
					this.directive();
					this.state = 48;
					this._errHandler.sync(this);
					_la = this._input.LA(1);
					while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 2076) !== 0)) {
						{
						{
						this.state = 45;
						this.filler();
						}
						}
						this.state = 50;
						this._errHandler.sync(this);
						_la = this._input.LA(1);
					}
					}
					}
				}
				this.state = 55;
				this._errHandler.sync(this);
				_alt = this._interp.adaptivePredict(this._input, 3, this._ctx);
			}
			this.state = 57;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===5) {
				{
				this.state = 56;
				this.lastDirective();
				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public filler(): FillerContext {
		let localctx: FillerContext = new FillerContext(this, this._ctx, this.state);
		this.enterRule(localctx, 4, RaslParser.RULE_filler);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 59;
			_la = this._input.LA(1);
			if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 2076) !== 0))) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public directive(): DirectiveContext {
		let localctx: DirectiveContext = new DirectiveContext(this, this._ctx, this.state);
		this.enterRule(localctx, 6, RaslParser.RULE_directive);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 61;
			this.header();
			this.state = 64;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 5, this._ctx) ) {
			case 1:
				{
				this.state = 62;
				this.separator();
				}
				break;
			case 2:
				{
				this.state = 63;
				this.block();
				}
				break;
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public lastDirective(): LastDirectiveContext {
		let localctx: LastDirectiveContext = new LastDirectiveContext(this, this._ctx, this.state);
		this.enterRule(localctx, 8, RaslParser.RULE_lastDirective);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 66;
			this.header();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public header(): HeaderContext {
		let localctx: HeaderContext = new HeaderContext(this, this._ctx, this.state);
		this.enterRule(localctx, 10, RaslParser.RULE_header);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 68;
			this.match(RaslParser.WORD);
			this.state = 69;
			this.rest();
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public rest(): RestContext {
		let localctx: RestContext = new RestContext(this, this._ctx, this.state);
		this.enterRule(localctx, 12, RaslParser.RULE_rest);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 77;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 7, this._ctx) ) {
			case 1:
				{
				this.state = 71;
				this.gap();
				this.state = 75;
				this._errHandler.sync(this);
				switch ( this._interp.adaptivePredict(this._input, 6, this._ctx) ) {
				case 1:
					{
					this.state = 72;
					this.value();
					this.state = 73;
					this.rest();
					}
					break;
				}
				}
				break;
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public gap(): GapContext {
		let localctx: GapContext = new GapContext(this, this._ctx, this.state);
		this.enterRule(localctx, 14, RaslParser.RULE_gap);
		let _la: number;
		try {
			let _alt: number;
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 80;
			this._errHandler.sync(this);
			_alt = 1;
			do {
				switch (_alt) {
				case 1:
					{
					{
					this.state = 79;
					_la = this._input.LA(1);
					if(!(_la===2 || _la===4)) {
					this._errHandler.recoverInline(this);
					}
					else {
						this._errHandler.reportMatch(this);
					    this.consume();
					}
					}
					}
					break;
				default:
					throw new NoViableAltException(this);
				}
				this.state = 82;
				this._errHandler.sync(this);
				_alt = this._interp.adaptivePredict(this._input, 8, this._ctx);
			} while (_alt !== 2 && _alt !== ATN.INVALID_ALT_NUMBER);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public separator(): SeparatorContext {
		let localctx: SeparatorContext = new SeparatorContext(this, this._ctx, this.state);
		this.enterRule(localctx, 16, RaslParser.RULE_separator);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 84;
			_la = this._input.LA(1);
			if(!(_la===3 || _la===11)) {
			this._errHandler.recoverInline(this);
			}
			else {
				this._errHandler.reportMatch(this);
			    this.consume();
			}
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public block(): BlockContext {
		let localctx: BlockContext = new BlockContext(this, this._ctx, this.state);
		this.enterRule(localctx, 18, RaslParser.RULE_block);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 86;
			if (!(true)) {
				throw this.createFailedPredicateException("true");
			}
			this.state = 87;
			this.match(RaslParser.LBRACE);
			this.state = 88;
			this.statements();
			this.state = 89;
			this.match(RaslParser.RBRACE);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public value(): ValueContext {
		let localctx: ValueContext = new ValueContext(this, this._ctx, this.state);
		this.enterRule(localctx, 20, RaslParser.RULE_value);
		try {
			this.state = 95;
			this._errHandler.sync(this);
			switch ( this._interp.adaptivePredict(this._input, 9, this._ctx) ) {
			case 1:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 91;
				this.match(RaslParser.WORD);
				}
				break;
			case 2:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 92;
				this.match(RaslParser.STRING);
				}
				break;
			case 3:
				this.enterOuterAlt(localctx, 3);
				{
				this.state = 93;
				this.slicedWord();
				}
				break;
			case 4:
				this.enterOuterAlt(localctx, 4);
				{
				this.state = 94;
				this.list();
				}
				break;
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public slicedWord(): SlicedWordContext {
		let localctx: SlicedWordContext = new SlicedWordContext(this, this._ctx, this.state);
		this.enterRule(localctx, 22, RaslParser.RULE_slicedWord);
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 97;
			this.match(RaslParser.WORD);
			this.state = 98;
			this.match(RaslParser.LBRACK);
			this.state = 99;
			this.bounds();
			this.state = 100;
			this.match(RaslParser.RBRACK);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public bounds(): BoundsContext {
		let localctx: BoundsContext = new BoundsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 24, RaslParser.RULE_bounds);
		let _la: number;
		try {
			this.state = 109;
			this._errHandler.sync(this);
			switch (this._input.LA(1)) {
			case 5:
				this.enterOuterAlt(localctx, 1);
				{
				this.state = 102;
				this.match(RaslParser.WORD);
				this.state = 103;
				this.match(RaslParser.COLON);
				this.state = 105;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if (_la===5) {
					{
					this.state = 104;
					this.match(RaslParser.WORD);
					}
				}

				}
				break;
			case 13:
				this.enterOuterAlt(localctx, 2);
				{
				this.state = 107;
				this.match(RaslParser.COLON);
				this.state = 108;
				this.match(RaslParser.WORD);
				}
				break;
			default:
				throw new NoViableAltException(this);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public list(): ListContext {
		let localctx: ListContext = new ListContext(this, this._ctx, this.state);
		this.enterRule(localctx, 26, RaslParser.RULE_list);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 111;
			this.match(RaslParser.LBRACK);
			this.state = 113;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 28) !== 0)) {
				{
				this.state = 112;
				this.listGap();
				}
			}

			this.state = 116;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 608) !== 0)) {
				{
				this.state = 115;
				this.items();
				}
			}

			this.state = 118;
			this.match(RaslParser.RBRACK);
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public items(): ItemsContext {
		let localctx: ItemsContext = new ItemsContext(this, this._ctx, this.state);
		this.enterRule(localctx, 28, RaslParser.RULE_items);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 120;
			this.value();
			this.state = 122;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 28) !== 0)) {
				{
				this.state = 121;
				this.listGap();
				}
			}

			this.state = 131;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			if (_la===12) {
				{
				this.state = 124;
				this.match(RaslParser.COMMA);
				this.state = 126;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 28) !== 0)) {
					{
					this.state = 125;
					this.listGap();
					}
				}

				this.state = 129;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
				if ((((_la) & ~0x1F) === 0 && ((1 << _la) & 608) !== 0)) {
					{
					this.state = 128;
					this.items();
					}
				}

				}
			}

			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}
	// @RuleVersion(0)
	public listGap(): ListGapContext {
		let localctx: ListGapContext = new ListGapContext(this, this._ctx, this.state);
		this.enterRule(localctx, 30, RaslParser.RULE_listGap);
		let _la: number;
		try {
			this.enterOuterAlt(localctx, 1);
			{
			this.state = 134;
			this._errHandler.sync(this);
			_la = this._input.LA(1);
			do {
				{
				{
				this.state = 133;
				_la = this._input.LA(1);
				if(!((((_la) & ~0x1F) === 0 && ((1 << _la) & 28) !== 0))) {
				this._errHandler.recoverInline(this);
				}
				else {
					this._errHandler.reportMatch(this);
				    this.consume();
				}
				}
				}
				this.state = 136;
				this._errHandler.sync(this);
				_la = this._input.LA(1);
			} while ((((_la) & ~0x1F) === 0 && ((1 << _la) & 28) !== 0));
			}
		}
		catch (re) {
			if (re instanceof RecognitionException) {
				localctx.exception = re;
				this._errHandler.reportError(this, re);
				this._errHandler.recover(this, re);
			} else {
				throw re;
			}
		}
		finally {
			this.exitRule();
		}
		return localctx;
	}

	public sempred(localctx: RuleContext, ruleIndex: number, predIndex: number): boolean {
		switch (ruleIndex) {
		case 9:
			return this.block_sempred(localctx as BlockContext, predIndex);
		}
		return true;
	}
	private block_sempred(localctx: BlockContext, predIndex: number): boolean {
		switch (predIndex) {
		case 0:
			return true;
		}
		return true;
	}

	public static readonly _serializedATN: number[] = [4,1,15,139,2,0,7,0,2,
	1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,6,2,7,7,7,2,8,7,8,2,9,7,9,2,
	10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,2,14,7,14,2,15,7,15,1,0,3,0,34,8,
	0,1,0,1,0,1,0,1,1,5,1,40,8,1,10,1,12,1,43,9,1,1,1,1,1,5,1,47,8,1,10,1,12,
	1,50,9,1,5,1,52,8,1,10,1,12,1,55,9,1,1,1,3,1,58,8,1,1,2,1,2,1,3,1,3,1,3,
	3,3,65,8,3,1,4,1,4,1,5,1,5,1,5,1,6,1,6,1,6,1,6,3,6,76,8,6,3,6,78,8,6,1,
	7,4,7,81,8,7,11,7,12,7,82,1,8,1,8,1,9,1,9,1,9,1,9,1,9,1,10,1,10,1,10,1,
	10,3,10,96,8,10,1,11,1,11,1,11,1,11,1,11,1,12,1,12,1,12,3,12,106,8,12,1,
	12,1,12,3,12,110,8,12,1,13,1,13,3,13,114,8,13,1,13,3,13,117,8,13,1,13,1,
	13,1,14,1,14,3,14,123,8,14,1,14,1,14,3,14,127,8,14,1,14,3,14,130,8,14,3,
	14,132,8,14,1,15,4,15,135,8,15,11,15,12,15,136,1,15,0,0,16,0,2,4,6,8,10,
	12,14,16,18,20,22,24,26,28,30,0,4,2,0,2,4,11,11,2,0,2,2,4,4,2,0,3,3,11,
	11,1,0,2,4,143,0,33,1,0,0,0,2,41,1,0,0,0,4,59,1,0,0,0,6,61,1,0,0,0,8,66,
	1,0,0,0,10,68,1,0,0,0,12,77,1,0,0,0,14,80,1,0,0,0,16,84,1,0,0,0,18,86,1,
	0,0,0,20,95,1,0,0,0,22,97,1,0,0,0,24,109,1,0,0,0,26,111,1,0,0,0,28,120,
	1,0,0,0,30,134,1,0,0,0,32,34,5,1,0,0,33,32,1,0,0,0,33,34,1,0,0,0,34,35,
	1,0,0,0,35,36,3,2,1,0,36,37,5,0,0,1,37,1,1,0,0,0,38,40,3,4,2,0,39,38,1,
	0,0,0,40,43,1,0,0,0,41,39,1,0,0,0,41,42,1,0,0,0,42,53,1,0,0,0,43,41,1,0,
	0,0,44,48,3,6,3,0,45,47,3,4,2,0,46,45,1,0,0,0,47,50,1,0,0,0,48,46,1,0,0,
	0,48,49,1,0,0,0,49,52,1,0,0,0,50,48,1,0,0,0,51,44,1,0,0,0,52,55,1,0,0,0,
	53,51,1,0,0,0,53,54,1,0,0,0,54,57,1,0,0,0,55,53,1,0,0,0,56,58,3,8,4,0,57,
	56,1,0,0,0,57,58,1,0,0,0,58,3,1,0,0,0,59,60,7,0,0,0,60,5,1,0,0,0,61,64,
	3,10,5,0,62,65,3,16,8,0,63,65,3,18,9,0,64,62,1,0,0,0,64,63,1,0,0,0,65,7,
	1,0,0,0,66,67,3,10,5,0,67,9,1,0,0,0,68,69,5,5,0,0,69,70,3,12,6,0,70,11,
	1,0,0,0,71,75,3,14,7,0,72,73,3,20,10,0,73,74,3,12,6,0,74,76,1,0,0,0,75,
	72,1,0,0,0,75,76,1,0,0,0,76,78,1,0,0,0,77,71,1,0,0,0,77,78,1,0,0,0,78,13,
	1,0,0,0,79,81,7,1,0,0,80,79,1,0,0,0,81,82,1,0,0,0,82,80,1,0,0,0,82,83,1,
	0,0,0,83,15,1,0,0,0,84,85,7,2,0,0,85,17,1,0,0,0,86,87,4,9,0,0,87,88,5,7,
	0,0,88,89,3,2,1,0,89,90,5,8,0,0,90,19,1,0,0,0,91,96,5,5,0,0,92,96,5,6,0,
	0,93,96,3,22,11,0,94,96,3,26,13,0,95,91,1,0,0,0,95,92,1,0,0,0,95,93,1,0,
	0,0,95,94,1,0,0,0,96,21,1,0,0,0,97,98,5,5,0,0,98,99,5,9,0,0,99,100,3,24,
	12,0,100,101,5,10,0,0,101,23,1,0,0,0,102,103,5,5,0,0,103,105,5,13,0,0,104,
	106,5,5,0,0,105,104,1,0,0,0,105,106,1,0,0,0,106,110,1,0,0,0,107,108,5,13,
	0,0,108,110,5,5,0,0,109,102,1,0,0,0,109,107,1,0,0,0,110,25,1,0,0,0,111,
	113,5,9,0,0,112,114,3,30,15,0,113,112,1,0,0,0,113,114,1,0,0,0,114,116,1,
	0,0,0,115,117,3,28,14,0,116,115,1,0,0,0,116,117,1,0,0,0,117,118,1,0,0,0,
	118,119,5,10,0,0,119,27,1,0,0,0,120,122,3,20,10,0,121,123,3,30,15,0,122,
	121,1,0,0,0,122,123,1,0,0,0,123,131,1,0,0,0,124,126,5,12,0,0,125,127,3,
	30,15,0,126,125,1,0,0,0,126,127,1,0,0,0,127,129,1,0,0,0,128,130,3,28,14,
	0,129,128,1,0,0,0,129,130,1,0,0,0,130,132,1,0,0,0,131,124,1,0,0,0,131,132,
	1,0,0,0,132,29,1,0,0,0,133,135,7,3,0,0,134,133,1,0,0,0,135,136,1,0,0,0,
	136,134,1,0,0,0,136,137,1,0,0,0,137,31,1,0,0,0,19,33,41,48,53,57,64,75,
	77,82,95,105,109,113,116,122,126,129,131,136];

	private static __ATN: ATN;
	public static get _ATN(): ATN {
		if (!RaslParser.__ATN) {
			RaslParser.__ATN = new ATNDeserializer().deserialize(RaslParser._serializedATN);
		}

		return RaslParser.__ATN;
	}


	static DecisionsToDFA = RaslParser._ATN.decisionToState.map( (ds: DecisionState, index: number) => new DFA(ds, index) );

}

export class DocumentContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public statements(): StatementsContext {
		return this.getTypedRuleContext(StatementsContext, 0) as StatementsContext;
	}
	public EOF(): TerminalNode {
		return this.getToken(RaslParser.EOF, 0);
	}
	public BOM(): TerminalNode {
		return this.getToken(RaslParser.BOM, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_document;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterDocument) {
	 		listener.enterDocument(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitDocument) {
	 		listener.exitDocument(this);
		}
	}
}


export class StatementsContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public filler_list(): FillerContext[] {
		return this.getTypedRuleContexts(FillerContext) as FillerContext[];
	}
	public filler(i: number): FillerContext {
		return this.getTypedRuleContext(FillerContext, i) as FillerContext;
	}
	public directive_list(): DirectiveContext[] {
		return this.getTypedRuleContexts(DirectiveContext) as DirectiveContext[];
	}
	public directive(i: number): DirectiveContext {
		return this.getTypedRuleContext(DirectiveContext, i) as DirectiveContext;
	}
	public lastDirective(): LastDirectiveContext {
		return this.getTypedRuleContext(LastDirectiveContext, 0) as LastDirectiveContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_statements;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterStatements) {
	 		listener.enterStatements(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitStatements) {
	 		listener.exitStatements(this);
		}
	}
}


export class FillerContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SPACE(): TerminalNode {
		return this.getToken(RaslParser.SPACE, 0);
	}
	public COMMENT(): TerminalNode {
		return this.getToken(RaslParser.COMMENT, 0);
	}
	public NEWLINE(): TerminalNode {
		return this.getToken(RaslParser.NEWLINE, 0);
	}
	public SEMI(): TerminalNode {
		return this.getToken(RaslParser.SEMI, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_filler;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterFiller) {
	 		listener.enterFiller(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitFiller) {
	 		listener.exitFiller(this);
		}
	}
}


export class DirectiveContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public header(): HeaderContext {
		return this.getTypedRuleContext(HeaderContext, 0) as HeaderContext;
	}
	public separator(): SeparatorContext {
		return this.getTypedRuleContext(SeparatorContext, 0) as SeparatorContext;
	}
	public block(): BlockContext {
		return this.getTypedRuleContext(BlockContext, 0) as BlockContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_directive;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterDirective) {
	 		listener.enterDirective(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitDirective) {
	 		listener.exitDirective(this);
		}
	}
}


export class LastDirectiveContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public header(): HeaderContext {
		return this.getTypedRuleContext(HeaderContext, 0) as HeaderContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_lastDirective;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterLastDirective) {
	 		listener.enterLastDirective(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitLastDirective) {
	 		listener.exitLastDirective(this);
		}
	}
}


export class HeaderContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WORD(): TerminalNode {
		return this.getToken(RaslParser.WORD, 0);
	}
	public rest(): RestContext {
		return this.getTypedRuleContext(RestContext, 0) as RestContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_header;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterHeader) {
	 		listener.enterHeader(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitHeader) {
	 		listener.exitHeader(this);
		}
	}
}


export class RestContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public gap(): GapContext {
		return this.getTypedRuleContext(GapContext, 0) as GapContext;
	}
	public value(): ValueContext {
		return this.getTypedRuleContext(ValueContext, 0) as ValueContext;
	}
	public rest(): RestContext {
		return this.getTypedRuleContext(RestContext, 0) as RestContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_rest;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterRest) {
	 		listener.enterRest(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitRest) {
	 		listener.exitRest(this);
		}
	}
}


export class GapContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SPACE_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.SPACE);
	}
	public SPACE(i: number): TerminalNode {
		return this.getToken(RaslParser.SPACE, i);
	}
	public COMMENT_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.COMMENT);
	}
	public COMMENT(i: number): TerminalNode {
		return this.getToken(RaslParser.COMMENT, i);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_gap;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterGap) {
	 		listener.enterGap(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitGap) {
	 		listener.exitGap(this);
		}
	}
}


export class SeparatorContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SEMI(): TerminalNode {
		return this.getToken(RaslParser.SEMI, 0);
	}
	public NEWLINE(): TerminalNode {
		return this.getToken(RaslParser.NEWLINE, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_separator;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterSeparator) {
	 		listener.enterSeparator(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitSeparator) {
	 		listener.exitSeparator(this);
		}
	}
}


export class BlockContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACE(): TerminalNode {
		return this.getToken(RaslParser.LBRACE, 0);
	}
	public statements(): StatementsContext {
		return this.getTypedRuleContext(StatementsContext, 0) as StatementsContext;
	}
	public RBRACE(): TerminalNode {
		return this.getToken(RaslParser.RBRACE, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_block;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterBlock) {
	 		listener.enterBlock(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitBlock) {
	 		listener.exitBlock(this);
		}
	}
}


export class ValueContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WORD(): TerminalNode {
		return this.getToken(RaslParser.WORD, 0);
	}
	public STRING(): TerminalNode {
		return this.getToken(RaslParser.STRING, 0);
	}
	public slicedWord(): SlicedWordContext {
		return this.getTypedRuleContext(SlicedWordContext, 0) as SlicedWordContext;
	}
	public list(): ListContext {
		return this.getTypedRuleContext(ListContext, 0) as ListContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_value;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterValue) {
	 		listener.enterValue(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitValue) {
	 		listener.exitValue(this);
		}
	}
}


export class SlicedWordContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WORD(): TerminalNode {
		return this.getToken(RaslParser.WORD, 0);
	}
	public LBRACK(): TerminalNode {
		return this.getToken(RaslParser.LBRACK, 0);
	}
	public bounds(): BoundsContext {
		return this.getTypedRuleContext(BoundsContext, 0) as BoundsContext;
	}
	public RBRACK(): TerminalNode {
		return this.getToken(RaslParser.RBRACK, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_slicedWord;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterSlicedWord) {
	 		listener.enterSlicedWord(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitSlicedWord) {
	 		listener.exitSlicedWord(this);
		}
	}
}


export class BoundsContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public WORD_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.WORD);
	}
	public WORD(i: number): TerminalNode {
		return this.getToken(RaslParser.WORD, i);
	}
	public COLON(): TerminalNode {
		return this.getToken(RaslParser.COLON, 0);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_bounds;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterBounds) {
	 		listener.enterBounds(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitBounds) {
	 		listener.exitBounds(this);
		}
	}
}


export class ListContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public LBRACK(): TerminalNode {
		return this.getToken(RaslParser.LBRACK, 0);
	}
	public RBRACK(): TerminalNode {
		return this.getToken(RaslParser.RBRACK, 0);
	}
	public listGap(): ListGapContext {
		return this.getTypedRuleContext(ListGapContext, 0) as ListGapContext;
	}
	public items(): ItemsContext {
		return this.getTypedRuleContext(ItemsContext, 0) as ItemsContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_list;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterList) {
	 		listener.enterList(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitList) {
	 		listener.exitList(this);
		}
	}
}


export class ItemsContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public value(): ValueContext {
		return this.getTypedRuleContext(ValueContext, 0) as ValueContext;
	}
	public listGap_list(): ListGapContext[] {
		return this.getTypedRuleContexts(ListGapContext) as ListGapContext[];
	}
	public listGap(i: number): ListGapContext {
		return this.getTypedRuleContext(ListGapContext, i) as ListGapContext;
	}
	public COMMA(): TerminalNode {
		return this.getToken(RaslParser.COMMA, 0);
	}
	public items(): ItemsContext {
		return this.getTypedRuleContext(ItemsContext, 0) as ItemsContext;
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_items;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterItems) {
	 		listener.enterItems(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitItems) {
	 		listener.exitItems(this);
		}
	}
}


export class ListGapContext extends ParserRuleContext {
	constructor(parser?: RaslParser, parent?: ParserRuleContext, invokingState?: number) {
		super(parent, invokingState);
    	this.parser = parser;
	}
	public SPACE_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.SPACE);
	}
	public SPACE(i: number): TerminalNode {
		return this.getToken(RaslParser.SPACE, i);
	}
	public COMMENT_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.COMMENT);
	}
	public COMMENT(i: number): TerminalNode {
		return this.getToken(RaslParser.COMMENT, i);
	}
	public NEWLINE_list(): TerminalNode[] {
	    	return this.getTokens(RaslParser.NEWLINE);
	}
	public NEWLINE(i: number): TerminalNode {
		return this.getToken(RaslParser.NEWLINE, i);
	}
    public get ruleIndex(): number {
    	return RaslParser.RULE_listGap;
	}
	public enterRule(listener: RaslListener): void {
	    if(listener.enterListGap) {
	 		listener.enterListGap(this);
		}
	}
	public exitRule(listener: RaslListener): void {
	    if(listener.exitListGap) {
	 		listener.exitListGap(this);
		}
	}
}
