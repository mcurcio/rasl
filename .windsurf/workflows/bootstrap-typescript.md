# Bootstrap TypeScript Project

Bootstrap a modern TypeScript project with tsx, eslint, prettier, and vitest configured according to best practices.

## Steps

1. **Initialize package.json**
   - Create a `package.json` file in the current workspace root
   - Set `"type": "module"` for ES modules
   - Set `"private": true`
   - Add the following scripts:
     ```json
     "scripts": {
       "build": "tsc",
       "test": "vitest",
       "dev": "tsx watch src/index.ts",
       "lint": "eslint src",
       "lint:fix": "eslint src --fix",
       "format": "prettier -w .",
       "format:check": "prettier -c .",
       "typecheck": "tsc --noEmit"
     }
     ```
   - Add these devDependencies:
     - `@types/node@^20.10.0`
     - `@typescript-eslint/eslint-plugin@^8.19.0`
     - `@typescript-eslint/parser@^8.19.0`
     - `eslint@^8.55.0`
     - `eslint-config-prettier@^9.1.0`
     - `eslint-plugin-simple-import-sort@^12.1.1`
     - `prettier@^3.1.0`
     - `tsx@^4.19.2`
     - `typescript@^5.3.0`
     - `vitest@^1.0.0`
   - Set `"engines": { "node": ">=18.0.0" }`

2. **Create tsconfig.json**
   - Create a `tsconfig.json` file with the following configuration:
     ```json
     {
       "compilerOptions": {
         "target": "ES2022",
         "module": "NodeNext",
         "moduleResolution": "NodeNext",
         "lib": ["ES2022"],
         "experimentalDecorators": true,
         "strict": true,
         "esModuleInterop": true,
         "skipLibCheck": true,
         "forceConsistentCasingInFileNames": true,
         "declaration": true,
         "declarationMap": true,
         "sourceMap": true,
         "outDir": "dist",
         "rootDir": "src",
         "resolveJsonModule": true,
         "isolatedModules": true,
         "noEmit": false,
         "noUnusedLocals": true,
         "noUnusedParameters": true,
         "noImplicitReturns": true,
         "noFallthroughCasesInSwitch": true
       },
       "include": ["src/**/*"]
     }
     ```

3. **Create eslint.config.js**
   - Create an `eslint.config.js` file with flat config format:
     ```javascript
     import tsParser from "@typescript-eslint/parser";
     import tsPlugin from "@typescript-eslint/eslint-plugin";
     import simpleImportSort from "eslint-plugin-simple-import-sort";
     import prettierConfig from "eslint-config-prettier";

     export default [
       {
         ignores: ["**/dist/**", "**/node_modules/**"],
       },
       prettierConfig,
       {
         files: ["**/*.ts", "**/*.tsx"],
         languageOptions: {
           parser: tsParser,
           parserOptions: {
             ecmaVersion: "latest",
             sourceType: "module",
           },
         },
         plugins: {
           "@typescript-eslint": tsPlugin,
           "simple-import-sort": simpleImportSort,
         },
         rules: {
           quotes: ["error", "double", { avoidEscape: true, allowTemplateLiterals: true }],
           semi: ["error", "always"],
           "@typescript-eslint/consistent-type-imports": [
             "error",
             { prefer: "type-imports", fixStyle: "separate-type-imports" },
           ],
           "simple-import-sort/imports": "error",
           "simple-import-sort/exports": "error",
         },
       },
     ];
     ```

4. **Create prettier.config.cjs**
   - Create a `prettier.config.cjs` file:
     ```javascript
     /** @type {import("prettier").Config} */
     module.exports = {
       printWidth: 120,
       semi: true,
       singleQuote: false,
       trailingComma: "all",
     };
     ```

5. **Create .prettierignore**
   - Create a `.prettierignore` file with:
     ```
     dist
     node_modules
     coverage
     .pnpm-store
     ```

6. **Create src directory and sample file**
   - Create a `src/` directory
   - Create `src/index.ts` with a simple example:
     ```typescript
     export function greet(name: string): string {
       return `Hello, ${name}!`;
     }

     console.log(greet("World"));
     ```

7. **Create .gitignore**
   - If `.gitignore` doesn't exist, create it with:
     ```
     node_modules
     dist
     coverage
     .pnpm-store
     *.log
     .DS_Store
     ```

8. **Install dependencies**
   - Run `npm install` to install all dependencies
   - Confirm installation was successful

9. **Verify setup**
   - Run `npm run typecheck` to verify TypeScript configuration
   - Run `npm run lint` to verify ESLint configuration
   - Run `npm run format:check` to verify Prettier configuration
   - Report any errors to the user

10. **Summary**
    - Print a summary of what was created
    - List the available npm scripts
    - Suggest next steps (e.g., "Run `npm run dev` to start development")
