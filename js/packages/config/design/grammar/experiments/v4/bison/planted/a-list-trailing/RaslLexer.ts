// Generated from Rasl.g4 by ANTLR 4.13.2
// noinspection ES6UnusedImports,JSUnusedGlobalSymbols,JSUnusedLocalSymbols
import {
	ATN,
	ATNDeserializer,
	CharStream,
	DecisionState, DFA,
	Lexer,
	LexerATNSimulator,
	RuleContext,
	PredictionContextCache,
	Token
} from "antlr4";
export default class RaslLexer extends Lexer {
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
	public static readonly EOF = Token.EOF;

	public static readonly channelNames: string[] = [ "DEFAULT_TOKEN_CHANNEL", "HIDDEN" ];
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
	public static readonly modeNames: string[] = [ "DEFAULT_MODE", ];

	public static readonly ruleNames: string[] = [
		"BOM", "SPACE", "NEWLINE", "COMMENT", "WORD", "STRING", "LBRACE", "RBRACE", 
		"LBRACK", "RBRACK", "SEMI", "COMMA", "COLON", "UNTERMINATED_STRING", "BAD_CHAR", 
		"CHAR",
	];


	constructor(input: CharStream) {
		super(input);
		this._interp = new LexerATNSimulator(this, RaslLexer._ATN, RaslLexer.DecisionsToDFA, new PredictionContextCache());
	}

	public get grammarFileName(): string { return "Rasl.g4"; }

	public get literalNames(): (string | null)[] { return RaslLexer.literalNames; }
	public get symbolicNames(): (string | null)[] { return RaslLexer.symbolicNames; }
	public get ruleNames(): string[] { return RaslLexer.ruleNames; }

	public get serializedATN(): number[] { return RaslLexer._serializedATN; }

	public get channelNames(): string[] { return RaslLexer.channelNames; }

	public get modeNames(): string[] { return RaslLexer.modeNames; }

	public static readonly _serializedATN: number[] = [4,0,15,134,6,-1,2,0,
	7,0,2,1,7,1,2,2,7,2,2,3,7,3,2,4,7,4,2,5,7,5,2,6,7,6,2,7,7,7,2,8,7,8,2,9,
	7,9,2,10,7,10,2,11,7,11,2,12,7,12,2,13,7,13,2,14,7,14,2,15,7,15,1,0,1,0,
	1,1,4,1,37,8,1,11,1,12,1,38,1,2,1,2,1,2,3,2,44,8,2,1,3,1,3,5,3,48,8,3,10,
	3,12,3,51,9,3,1,4,1,4,5,4,55,8,4,10,4,12,4,58,9,4,1,4,1,4,5,4,62,8,4,10,
	4,12,4,65,9,4,3,4,67,8,4,1,5,1,5,1,5,1,5,5,5,73,8,5,10,5,12,5,76,9,5,1,
	5,1,5,1,5,1,5,1,5,5,5,83,8,5,10,5,12,5,86,9,5,1,5,3,5,89,8,5,1,6,1,6,1,
	7,1,7,1,8,1,8,1,9,1,9,1,10,1,10,1,11,1,11,1,12,1,12,1,13,1,13,1,13,1,13,
	5,13,109,8,13,10,13,12,13,112,9,13,1,13,3,13,115,8,13,1,13,1,13,1,13,1,
	13,5,13,121,8,13,10,13,12,13,124,9,13,1,13,3,13,127,8,13,3,13,129,8,13,
	1,14,1,14,1,15,1,15,0,0,16,1,1,3,2,5,3,7,4,9,5,11,6,13,7,15,8,17,9,19,10,
	21,11,23,12,25,13,27,14,29,15,31,0,1,0,9,2,0,9,9,32,32,5,0,42,42,46,47,
	63,90,95,95,97,122,6,0,35,35,42,43,45,58,63,90,95,95,97,122,2,0,45,45,48,
	57,6,0,35,35,42,43,45,57,63,90,95,95,97,122,6,0,0,8,10,31,34,34,92,92,127,
	127,55296,57343,6,0,0,8,10,31,39,39,92,92,127,127,55296,57343,12,0,9,10,
	32,32,34,35,39,39,42,42,44,59,63,91,93,93,95,95,97,123,125,125,65279,65279,
	4,0,9,9,32,126,128,55295,57344,1114111,150,0,1,1,0,0,0,0,3,1,0,0,0,0,5,
	1,0,0,0,0,7,1,0,0,0,0,9,1,0,0,0,0,11,1,0,0,0,0,13,1,0,0,0,0,15,1,0,0,0,
	0,17,1,0,0,0,0,19,1,0,0,0,0,21,1,0,0,0,0,23,1,0,0,0,0,25,1,0,0,0,0,27,1,
	0,0,0,0,29,1,0,0,0,1,33,1,0,0,0,3,36,1,0,0,0,5,43,1,0,0,0,7,45,1,0,0,0,
	9,66,1,0,0,0,11,88,1,0,0,0,13,90,1,0,0,0,15,92,1,0,0,0,17,94,1,0,0,0,19,
	96,1,0,0,0,21,98,1,0,0,0,23,100,1,0,0,0,25,102,1,0,0,0,27,128,1,0,0,0,29,
	130,1,0,0,0,31,132,1,0,0,0,33,34,5,65279,0,0,34,2,1,0,0,0,35,37,7,0,0,0,
	36,35,1,0,0,0,37,38,1,0,0,0,38,36,1,0,0,0,38,39,1,0,0,0,39,4,1,0,0,0,40,
	44,5,10,0,0,41,42,5,13,0,0,42,44,5,10,0,0,43,40,1,0,0,0,43,41,1,0,0,0,44,
	6,1,0,0,0,45,49,5,35,0,0,46,48,3,31,15,0,47,46,1,0,0,0,48,51,1,0,0,0,49,
	47,1,0,0,0,49,50,1,0,0,0,50,8,1,0,0,0,51,49,1,0,0,0,52,56,7,1,0,0,53,55,
	7,2,0,0,54,53,1,0,0,0,55,58,1,0,0,0,56,54,1,0,0,0,56,57,1,0,0,0,57,67,1,
	0,0,0,58,56,1,0,0,0,59,63,7,3,0,0,60,62,7,4,0,0,61,60,1,0,0,0,62,65,1,0,
	0,0,63,61,1,0,0,0,63,64,1,0,0,0,64,67,1,0,0,0,65,63,1,0,0,0,66,52,1,0,0,
	0,66,59,1,0,0,0,67,10,1,0,0,0,68,74,5,34,0,0,69,73,8,5,0,0,70,71,5,92,0,
	0,71,73,3,31,15,0,72,69,1,0,0,0,72,70,1,0,0,0,73,76,1,0,0,0,74,72,1,0,0,
	0,74,75,1,0,0,0,75,77,1,0,0,0,76,74,1,0,0,0,77,89,5,34,0,0,78,84,5,39,0,
	0,79,83,8,6,0,0,80,81,5,92,0,0,81,83,3,31,15,0,82,79,1,0,0,0,82,80,1,0,
	0,0,83,86,1,0,0,0,84,82,1,0,0,0,84,85,1,0,0,0,85,87,1,0,0,0,86,84,1,0,0,
	0,87,89,5,39,0,0,88,68,1,0,0,0,88,78,1,0,0,0,89,12,1,0,0,0,90,91,5,123,
	0,0,91,14,1,0,0,0,92,93,5,125,0,0,93,16,1,0,0,0,94,95,5,91,0,0,95,18,1,
	0,0,0,96,97,5,93,0,0,97,20,1,0,0,0,98,99,5,59,0,0,99,22,1,0,0,0,100,101,
	5,44,0,0,101,24,1,0,0,0,102,103,5,58,0,0,103,26,1,0,0,0,104,110,5,34,0,
	0,105,109,8,5,0,0,106,107,5,92,0,0,107,109,3,31,15,0,108,105,1,0,0,0,108,
	106,1,0,0,0,109,112,1,0,0,0,110,108,1,0,0,0,110,111,1,0,0,0,111,114,1,0,
	0,0,112,110,1,0,0,0,113,115,5,92,0,0,114,113,1,0,0,0,114,115,1,0,0,0,115,
	129,1,0,0,0,116,122,5,39,0,0,117,121,8,6,0,0,118,119,5,92,0,0,119,121,3,
	31,15,0,120,117,1,0,0,0,120,118,1,0,0,0,121,124,1,0,0,0,122,120,1,0,0,0,
	122,123,1,0,0,0,123,126,1,0,0,0,124,122,1,0,0,0,125,127,5,92,0,0,126,125,
	1,0,0,0,126,127,1,0,0,0,127,129,1,0,0,0,128,104,1,0,0,0,128,116,1,0,0,0,
	129,28,1,0,0,0,130,131,8,7,0,0,131,30,1,0,0,0,132,133,7,8,0,0,133,32,1,
	0,0,0,19,0,38,43,49,56,63,66,72,74,82,84,88,108,110,114,120,122,126,128,
	0];

	private static __ATN: ATN;
	public static get _ATN(): ATN {
		if (!RaslLexer.__ATN) {
			RaslLexer.__ATN = new ATNDeserializer().deserialize(RaslLexer._serializedATN);
		}

		return RaslLexer.__ATN;
	}


	static DecisionsToDFA = RaslLexer._ATN.decisionToState.map( (ds: DecisionState, index: number) => new DFA(ds, index) );
}