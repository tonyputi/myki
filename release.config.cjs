/**
 * Semantic Release configuration.
 *
 * - versions follow the repo history (baseline tag v0.1.0, next is v0.2.0)
 * - `prepare` bumps custom_components/myki/manifest.json so Home Assistant
 *   and the Marketplace always see the released version
 */
module.exports = {
    branches: ['main'],
    plugins: [
        '@semantic-release/commit-analyzer',
        '@semantic-release/release-notes-generator',
        ['@semantic-release/exec', {
            prepareCmd: 'python3 -c "import json,sys; p=\'custom_components/myki/manifest.json\'; d=json.load(open(p)); d[\'version\']=\'${nextRelease.version}\'; json.dump(d, open(p,\'w\'), indent=4)"',
        }],
        ['@semantic-release/git', {
            assets: ['custom_components/myki/manifest.json'],
            message: 'chore(release): ${nextRelease.version} [skip ci]',
        }],
        '@semantic-release/github',
    ],
};
