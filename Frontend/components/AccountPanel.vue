<template>
	<view class="account-panel">
		<text class="section-title">{{
			registering ? "注册账号，记住每笔工钱" : "登录工明白"
		}}</text>
		<text class="muted intro">{{
			registering
				? "设置账号和密码，下次登录继续查看账本。"
				: "让每一天的工钱都有据可查。"
		}}</text>
		<view class="field"
			><text>手机号</text
			><input
				aria-label="手机号"
				v-model="phone"
				type="number"
				maxlength="11"
				placeholder="请输入11位手机号"
		/></view>
		<view class="field"
			><text>密码</text
			><input
				aria-label="密码"
				v-model="password"
				:password="true"
				placeholder="8至72位密码"
		/></view>
		<view v-if="registering" class="field"
			><text>确认密码</text
			><input
				aria-label="确认密码"
				v-model="confirmation"
				:password="true"
				placeholder="再输入一次密码"
		/></view>
		<view v-if="error" class="notice" role="alert">{{ error }}</view>
		<button hover-class="none" class="primary" :disabled="loading" @click="submit">
			{{ loading ? "正在处理…" : registering ? "注册并登录" : "登录" }}
		</button>
		<button hover-class="none"
			class="secondary"
			:disabled="loading"
			@click="
				registering = !registering;
				error = '';
			"
		>
			{{ registering ? "已有账号，去登录" : "没有账号，去注册" }}
		</button>
		<button hover-class="none"
			v-if="guestEnabled"
			class="text-button"
			:disabled="loading"
			@click="guest"
		>
			先体验一下
		</button>
	</view>
</template>
<script setup>
import { ref } from "vue";
import { authenticate, guestSession } from "../services/api";
const emit = defineEmits(["success"]);
defineProps({ guestEnabled: { type: Boolean, default: true } });
const phone = ref(""),
	password = ref(""),
	confirmation = ref(""),
	registering = ref(false),
	loading = ref(false),
	error = ref("");
async function submit() {
	if (loading.value) return;
	if (!/^1\d{10}$/.test(phone.value)) {
		error.value = "请输入11位手机号";
		return;
	}
	if (password.value.length < 8 || password.value.length > 72) {
		error.value = "密码长度应为8至72位";
		return;
	}
	if (registering.value && password.value !== confirmation.value) {
		error.value = "两次输入的密码不同";
		return;
	}
	loading.value = true;
	error.value = "";
	try {
		await authenticate(
			registering.value ? "register" : "login",
			phone.value,
			password.value,
		);
		password.value = "";
		confirmation.value = "";
		emit("success");
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
}
async function guest() {
	loading.value = true;
	error.value = "";
	try {
		await guestSession();
		emit("success");
	} catch (e) {
		error.value = e.message;
	} finally {
		loading.value = false;
	}
}
</script>
<style scoped>
.account-panel {
	padding-top: 40px;
}
.account-panel .field {
	margin: 14px 0;
}
.account-panel .field input {
	width: 64%;
	text-align: left;
}
.account-panel > .text-button {
	display: flex;
	margin: 20px auto;
}
</style>
