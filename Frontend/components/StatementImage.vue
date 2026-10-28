<template>
	<view>
		<button hover-class="none" class="secondary" :disabled="saving || busy" :loading="saving" @click="save">{{ saving ? '正在保存图片…' : '保存对账单图片' }}</button>
		<text v-if="feedback" class="muted block" role="status">{{ feedback }}</text>
		<canvas
			canvas-id="statement"
			id="statement"
			style="
				position: fixed;
				left: -2000px;
				top: 0;
				width: 320px;
				height: 430px;
			"
		/>
	</view>
</template>
<script setup>
import { getCurrentInstance, ref } from "vue";
import { money } from "../services/api";
const props = defineProps({ project: Object, totals: Object, busy:Boolean });
const saving=ref(false),feedback=ref('');
function failed(message){saving.value=false;feedback.value=message;uni.showToast({title:message,icon:'none'});}
const instance = getCurrentInstance();
function save() {
	if(saving.value||props.busy)return;
	saving.value=true;feedback.value='';
	try{
	const c = uni.createCanvasContext("statement", instance.proxy);
	c.setFillStyle("#ffffff");
	c.fillRect(0, 0, 320, 430);
	c.setFillStyle("#117c0d");
	c.fillRect(0, 0, 320, 80);
	c.setFillStyle("#ffffff");
	c.setFontSize(28);
	c.fillText("工明白 · 对账单", 22, 51);
	c.setFillStyle("#17232c");
	c.setFontSize(19);
	c.fillText(props.project.name.slice(0, 15), 22, 120);
	c.setFontSize(17);
	c.fillText("与 " + props.project.boss.slice(0, 15) + " 核对", 22, 151);
	const rows = [
		["已记工钱", props.totals.wage_fen],
		["已收/借支", props.totals.advance_fen],
		["当前待收", props.totals.balance_fen],
	];
	rows.forEach(([label, value], i) => {
		c.setFillStyle(i === 2 ? "#a94c0b" : "#17232c");
		c.setFontSize(19);
		c.fillText(label, 22, 215 + i * 52);
		c.setTextAlign("right");
		c.fillText("¥" + money(value), 298, 215 + i * 52);
		c.setTextAlign("left");
	});
	c.setFillStyle("#657587");
	c.setFontSize(13);
	c.fillText(
		"截至 " + new Date(Date.now() + 8 * 3600000).toISOString().slice(0, 10),
		22,
		378,
	);
	c.fillText("由本人账本整理，供双方核对使用", 22, 403);
	c.draw(false, () =>
		uni.canvasToTempFilePath(
			{
				canvasId: "statement",
				success: (r) => {
					// #ifdef H5
					uni.previewImage({ urls: [r.tempFilePath], success:()=>{saving.value=false;feedback.value='图片已生成，可长按保存';},fail:()=>failed('图片预览失败，请重试') });
					// #endif
					// #ifndef H5
					uni.saveImageToPhotosAlbum({
						filePath: r.tempFilePath,
						success:()=>{saving.value=false;feedback.value='对账单图片已保存到相册';uni.showToast({title:'已保存到相册',icon:'success'});},
						fail: () =>
							{saving.value=false;feedback.value='未保存，请检查相册权限后重试';uni.showModal({
								title: "未保存",
								content: "请检查相册权限后重试",
								showCancel: false,
							});},
					});
					// #endif
				},
				fail: () =>
					failed('生成图片失败，请重试'),
			},
			instance.proxy,
		),
	);
	}catch{failed('生成图片失败，请重试');}
}
</script>
