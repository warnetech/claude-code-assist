// Minimal flat config so `npm run lint` is runnable. Deliberately narrow:
// it enforces parsing and unused-variable hygiene, not a style opinion.
export default [
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: {
        // Cloudflare Worker + Node + Jest
        console: "readonly",
        process: "readonly",
        Buffer: "readonly",
        fetch: "readonly",
        Response: "readonly",
        Request: "readonly",
        URL: "readonly",
        TextEncoder: "readonly",
        TextDecoder: "readonly",
        crypto: "readonly",
        describe: "readonly",
        test: "readonly",
        it: "readonly",
        expect: "readonly",
        beforeEach: "readonly",
        afterEach: "readonly",
        jest: "readonly",
      },
    },
    rules: {
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
      "no-undef": "error",
    },
  },
  { ignores: ["node_modules/**", ".wrangler/**", "dist/**", ".venv/**"] },
];
