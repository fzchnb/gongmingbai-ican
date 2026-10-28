import test from 'node:test';
import assert from 'node:assert/strict';
import {syncReceiptForms} from '../services/receiptForms.mjs';

test('receipt suggestion initializes date, refreshes untouched values, preserves edits and intentional empty date',()=>{
 const forms={};
 syncReceiptForms(forms,[{id:'one',amount_fen:4000,date:'2026-10-20'}]);
 assert.equal(forms.one.date,'2026-10-20');assert.equal(forms.one.amount,'40');
 syncReceiptForms(forms,[{id:'one',amount_fen:5000,date:'2026-10-21'}]);
 assert.equal(forms.one.date,'2026-10-21');assert.equal(forms.one.amount,'50');
 forms.one.date='2026-10-25';forms.one.amount='45';
 syncReceiptForms(forms,[{id:'one',amount_fen:6000,date:'2026-10-22'},{id:'two',amount_fen:900,date:null}]);
 assert.equal(forms.one.date,'2026-10-25');assert.equal(forms.one.amount,'45');
 assert.equal(forms.two.date,'');assert.equal(forms.two.amount,'9');
 // Even if a new suggestion temporarily matches the edit, later refreshes
 // must still respect the person's choice.
 syncReceiptForms(forms,[{id:'one',amount_fen:4500,date:'2026-10-25'}]);
 syncReceiptForms(forms,[{id:'one',amount_fen:6000,date:'2026-10-22'}]);
 assert.equal(forms.one.date,'2026-10-25');assert.equal(forms.one.amount,'45');
 forms.one.date='';
 syncReceiptForms(forms,[{id:'one',amount_fen:6000,date:'2026-10-22'}]);
 assert.equal(forms.one.date,'');
});
