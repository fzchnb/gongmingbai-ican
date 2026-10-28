const fs = require('fs')
const m = require('json5').parse(fs.readFileSync('manifest.json', 'utf8'))
m.name = '工明白'
m.description = '零工劳动者的AI务工助手'
m['app-plus'].modules = { Record: {} }
m['app-plus'].distribute.android.packagename = 'com.gongmingbai.app'
m['app-plus'].distribute.android.permissions = ['INTERNET', 'RECORD_AUDIO', 'ACCESS_NETWORK_STATE'].map(name => `<uses-permission android:name="android.permission.${name}"/>`)
fs.writeFileSync('manifest.json', JSON.stringify(m, null, 2))
