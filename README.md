<a name="readme-top"></a>

<!-- PROJECT LOGO -->
<br />
<div align="center">
  <h2>Cheshire-Cat (Stregatto)</h2>
<br/>
  <a href="https://github.com/ai-blackbird/cheshirecat-core">
  <img alt="GitHub Repo stars" src="https://img.shields.io/github/stars/ai-blackbird/cheshirecat-core?style=social">
</a>
  <a href="https://discord.gg/bHX5sNFCYU">
        <img src="https://img.shields.io/discord/1092359754917089350?logo=discord"
            alt="chat on Discord"></a>
  <a href="https://github.com/ai-blackbird/cheshirecat-core/issues">
  <img alt="GitHub issues" src="https://img.shields.io/github/issues/ai-blackbird/cheshirecat-core">
  </a>
  <a href="https://github.com/ai-blackbird/cheshirecat-core/tags">
  <img alt="GitHub tag (with filter)" src="https://img.shields.io/github/v/tag/ai-blackbird/cheshirecat-core">
  </a>
  <img alt="GitHub top language" src="https://img.shields.io/github/languages/top/ai-blackbird/cheshirecat-core">

  <br/>
  <video src="https://github.com/cheshire-cat-ai/core/assets/6328377/7bc4acff-34bf-4b8a-be61-4d8967fbd60f"></video>
</div>

## Production ready AI assistant framework

The Cheshire Cat is a framework to build custom AIs on top of any language model. 
If you have ever used systems like WordPress or Django to build web apps, imagine the Cat as a similar tool, but specific for AI.

The current version is a multi-tenant fork of the original [Cheshire Cat](https://github.com/cheshire-cat-ai/core).
The original project is developed as a framework that could be used for a personal use as well as for single-tenant production.
In the latter case, the original [documentation](https://cheshire-cat-ai.github.io/docs/) clearly states to set up a secure environment
by using an API Key. If not configured properly (e.g. by setting up an API Key), the current version will not work, indeed.
In this way, I tried to make the Cat more secure and production-ready.

Moreover, this version can be deployed in a cluster environment. Whilst the original version stored the settings into
JSON files, our version requires a Redis database to store the  settings, the conversation histories, the plugins and so
forth. You can configure the Redis database by environment variables. The [`compose.yml`](./compose.yml) file is provided as an example.

The Cat is still stateless, so it can be easily scaled.
In case of a cluster environment, we suggest to use a shared storage, mounted in the `cat/plugins` folder, to share the plugins.

Hence, the current version is multi-tenant, meaning that you can manage multiple RAGs and other language models at the same time.

Here, the structure used for configuring `Embedder`, `LLMs`, `Authorization Handler` and `File Manager` is different from the original version:
interfaces and factories have been used for the scope.

Here, I have introduced some new features and improvements, such as:
- The `Embedder` is centralized and can be used by multiple RAGs and other language models.
- A new `File Manager` that allows you to store files, injected to the RAG, into a remote storage.
- New admin endpoints allowing to configure the `Embedder` and `File Manager`.
- A new event system that allows you to get fine-grained control over the AI.
- **The ability to manage multiple RAGs and other language models at the same time**.

This new version is completely compatible with the original version, so you can easily migrate your existing plugins
and settings to the new version. It is still in development, but you can already try it out by running the Docker image.
New features will be added in the future. Please contact us if you want to contribute.

## Quickstart

To make Cheshire Cat run on your machine, you just need [`docker`](https://docs.docker.com/get-docker/) installed:

```bash
docker run --rm -it -p 1865:80 ghcr.io/matteocacciola/cheshirecat-core:latest
```
- Chat with the Cheshire Cat on [localhost:1865/docs](http://localhost:1865/docs).

Since this version is intended as a microservice, the `admin` panel is no longer available. You can still use widgets from
the [original project](https://github.com/cheshire-cat-ai/) to manage the Cat.

As a first thing, the Cat will ask you to configure your favourite language model.
It can be done directly via the interface in the Settings page (top right in the admin).

Enjoy the Cat!  
Follow instructions on how to run it with [docker compose and volumes](https://cheshire-cat-ai.github.io/docs/quickstart/installation-configuration/).

## Minimal plugin example

```python
from cat.mad_hatter.decorators import tool, hook

# hooks are an event system to get finegraned control over your assistant
@hook
def agent_prompt_prefix(prefix, cat):
    prefix = """You are Marvin the socks seller, a poetic vendor of socks.
You are an expert in socks, and you reply with exactly one rhyme.
"""
    return prefix

# langchain inspired tools (function calling)
@tool(return_direct=True)
def socks_prices(color, cat):
    """How much do socks cost? Input is the sock color."""
    prices = {
        "black": 5,
        "white": 10,
        "pink": 50,
    }

    price = prices.get(color, 0)
    return f"{price} bucks, meeeow!" 
```

## Conversational form example

```python
from pydantic import BaseModel
from cat.experimental.form import form, CatForm

# data structure to fill up
class PizzaOrder(BaseModel):
    pizza_type: str
    phone: int

# forms let you control goal oriented conversations
@form
class PizzaForm(CatForm):
    description = "Pizza Order"
    model_class = PizzaOrder
    start_examples = [
        "order a pizza!",
        "I want pizza"
    ]
    stop_examples = [
        "stop pizza order",
        "not hungry anymore",
    ]
    ask_confirm = True

    def submit(self, form_data):
        
        # do the actual order here!

        # return to convo
        return {
            "output": f"Pizza order on its way: {form_data}"
        }
```

## Docs and Resources

- [Official Documentation](https://cheshire-cat-ai.github.io/docs/)
- [Discord Server](https://discord.gg/bHX5sNFCYU)
- [Website](https://cheshirecat.ai/)
- [YouTube tutorial - How to install](https://youtu.be/Rvx19TZBCrw)
- [Tutorial - Write your first plugin](https://cheshirecat.ai/write-your-first-plugin/)

## Why use the Cat

- ⚡️ API first, so you get a microservice to easily add a conversational layer to your app
- 🐘 Remembers conversations and documents and uses them in conversation
- 🚀 Extensible via plugins (public plugin registry + private plugins allowed)
- 🎚 Event callbacks, function calling (tools), conversational forms
- 🏛 Easy to use admin panel (chat, visualize memory and plugins, adjust settings)
- 🌍 Supports any language model (works with OpenAI, Google, Ollama, HuggingFace, custom services)
- 🐋 Production ready - 100% [dockerized](https://docs.docker.com/get-docker/)
- 👩‍👧‍👦 Active [Discord community](https://discord.gg/bHX5sNFCYU) and easy to understand [docs](https://cheshire-cat-ai.github.io/docs/)
 
We are committed to openness, privacy and creativity, we want to bring AI to the long tail. If you want to know more
about our vision and values, read the [Code of Ethics](./CODE-OF-ETHICS.md). 


## Roadmap & Contributing

Send your pull request to the `develop` branch. Here is a [full guide to contributing](CONTRIBUTING.md).

Join our [community on Discord](https://discord.gg/bHX5sNFCYU) and give the project a star ⭐!
Thanks again!🙏

## Which way to go?

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<p align="center">
    <img align="center" src=./readme/cheshire-cat.jpeg width=400px alt="Wikipedia picture of the Cheshire Cat">
</p>

```
"Would you tell me, please, which way I ought to go from here?"
"That depends a good deal on where you want to get to," said the Cat.
"I don't much care where--" said Alice.
"Then it doesn't matter which way you go," said the Cat.

(Alice's Adventures in Wonderland - Lewis Carroll)

```
