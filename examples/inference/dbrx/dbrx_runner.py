import torch
from dbrx.neuron_modeling_dbrx import (
    NeuronDbrxConfig,
    NeuronDbrxForCausalLM,
    NeuronDbrxModel,
)
from runner import InferenceRunner
from transformers import AutoTokenizer, DbrxConfig

from neuronx_distributed.parallel_layers.checkpointing import _invoke_preshard_hook


class DbrxRunner(InferenceRunner):
    def load_hf_model(self):
        hf_config = DbrxConfig.from_pretrained(self.model_path)
        return NeuronDbrxForCausalLM.load_hf_model(self.model_path, hf_config)

    def load_neuron_model_on_cpu(self, max_prompt_length, sequence_length, batch_size, **kwargs):
        # On CPU we can only run tensor parallelism with degree 1
        hf_config = self.get_hf_config(sequence_length=sequence_length, **kwargs)
        neuron_config = self.get_config_for_nxd(
            hf_config,
            batch_size,
            1,
            max_prompt_length=max_prompt_length,
            sequence_length=sequence_length,
            enable_bucketing=False,
            **kwargs)
        hf_config.torch_dtype = torch.float32

        self.init_ditributed_env()
        neuron_model = NeuronDbrxModel(neuron_config)

        state_dict = NeuronDbrxForCausalLM.get_state_dict(self.model_path, neuron_config)

        _invoke_preshard_hook(neuron_model, state_dict)

        neuron_model.load_state_dict(state_dict, strict=False)

        if hf_config.torch_dtype == torch.bfloat16:
            neuron_model.bfloat16()

        model = NeuronDbrxForCausalLM(None, neuron_config)
        model.context_encoding_model.model = neuron_model
        model.token_generation_model.model = neuron_model
        return model

    def load_tokenizer(self, padding_side=None):
        tokenizer = AutoTokenizer.from_pretrained(self.tokenizer_path)
        tokenizer.pad_token = tokenizer.unk_token
        tokenizer.padding_side = padding_side if padding_side else self.get_padding_side()
        return tokenizer

    def get_config_cls(self):
        return NeuronDbrxConfig

    def get_model_cls(self):
        return NeuronDbrxForCausalLM

    def get_padding_side(self):
        return "right"

    def get_default_hf_generation_config_kwargs(self):
        config = super().get_default_hf_generation_config_kwargs()
        config['pad_token_id'] = 0

        return config


if __name__ == "__main__":
    DbrxRunner.cmd_execute()
