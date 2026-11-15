/**
 * Semantic Release configuration.
 *
 * - versions follow the repo history (baseline tag v0.1.0, next is v0.2.0)
 * - `prepare` versions the manifest and packages the HACS release asset
 */
module.exports = {
    branches: ['main'],
    plugins: [
        '@semantic-release/commit-analyzer',
        '@semantic-release/release-notes-generator',
        ['@semantic-release/exec', {
            prepareCmd: 'python3 -c "import json; p=\'custom_components/myki/manifest.json\'; d=json.load(open(p)); d[\'version\']=\'${nextRelease.version}\'; json.dump(d, open(p,\'w\'), indent=4)" && cd custom_components/myki && zip -qr ../../myki.zip .',
        }],
        ['@semantic-release/github', { assets: ['myki.zip'] }],
    ],
};
