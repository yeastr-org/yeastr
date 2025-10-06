#!/bin/bash
set -e  # stop on errors
set -x  # enable bash debugging

CUR_DIR=$PWD
WHLS=$CUR_DIR/downloads
CI_DIR=/tmp/yeastr-localci
LAYOUT_SRC=/tmp/yeastr-test-proj
LAYOUT_SCRIPT=/tmp/yeastr-test-script
STORE_DIR=$CUR_DIR/../yeastr-test-proj/localci
#PY313=/root/wip/wip/Python-3.13.7/python
PY314=/root/wip/wip/Python-3.14.0rc3/python
# STORE_DIR abuses yeastr-test-proj, but contains all the layouts results
mkdir -p $STORE_DIR/out

FAILED=0

case $1 in
  download)
    mkdir -p $WHLS
    cd $WHLS
        for whl in `ls $CUR_DIR/*.whl` ; do
            mv $whl $whl.bak
        done
        pip download \
            build \
            pyproject_hooks \
            setuptools \
            wheel \
            packaging
  ;;
  run)
    rm -rf $CI_DIR
    mkdir -p $CI_DIR/out
    rm -rf yeastr-*.egg-info
    rm -rf build
    if [[ $2 != 'skip-build' ]]; then
        echo 'first bootstrap'  # use old to build the new
        python bootstrap.py
        echo 'second bootstrap' # use the new to rebuild the new
        python bootstrap.py
        # echo 'third bootstrap'# use the newnew to rebuild newnewnew
        # python bootstrap.py
        # i mean, it happened to need the third but it's less likely to happen
        # i mean, just silly to make 3-4 times all the time, 2 usually enough
    fi

    rm -rf $LAYOUT_SRC
    mkdir -p $LAYOUT_SRC
    cp -r $CUR_DIR/../yeastr-test-proj/* $LAYOUT_SRC
    cd $LAYOUT_SRC
        virtualenv -p $PY314 venv-py314
        set +x ; echo 'activate venv-py314'  # that's too verbose
        . venv-py314/bin/activate
        set -x
        echo "well, if you wonder why I'm installing wheels instead of testing the deps management"
        echo "this is still unreleased, and this is just for my machine"
        pip install $CUR_DIR/dist/yeastr-0.0.1-py314-none-any.whl --force-reinstall
        # f*ck let me do stuff offline.
        # (happened again to forget --no-deps)
        for whl in `ls $WHLS/*.whl`; do
            pip install $whl --no-deps
        done
        pip list

        #read -p "Do you want to continue? (y/n) " -n 1 -r
        #if [[ $REPLY != y ]]; then
        #  exit 1
        #fi

        rm -rf yeastr_test.egg-info/
        rm -rf build/
        python -m build --no-isolation
        set +x ; echo 'deactivate venv-py314'  # that's too verbose
        deactivate
        set -x


    echo 'going away from that dir, so sys.path is clean'
    cd $CI_DIR

        virtualenv -p $PY314 yeastr-venv-srctest-py314
        set +x ; echo 'activate yeastr-venv-srctest-py314'
        . yeastr-venv-srctest-py314/bin/activate
        set -x
        pip install $CUR_DIR/dist/yeastr-0.0.1-py314-none-any.whl --force-reinstall
        python -m yeastr.packaging_test > ./out/yeastr_test_packaging_py314
        diff ./out/yeastr_test_packaging_py314 $STORE_DIR/out/yeastr_test_packaging
        pip install $LAYOUT_SRC/dist/yeastr_test-0.0.1-py314-none-any.whl --force-reinstall --no-deps
        pip list
        echo 'Launch some examples'
        python -m yeastr_test.call2comp > ./out/src_call2comp_py314
        python -m yeastr_test.namedloops > ./out/src_namedloops_py314
        python -m yeastr_test.macros > ./out/src_macros_py314
        python -m yeastr_test.test_match_game > ./out/src_match_game_py314
        python -m yeastr_test.macros_test > ./out/src_macros_test_py314
        python -m yeastr_test.backporting_dict_ops > ./out/src_dictops_py314
        set +x ; echo 'deactivate yeastr-venv-srctest-py314'
        deactivate
        set -x

        virtualenv -p python3.8 yeastr-venv-srctest-py38
        set +x ; echo 'activate yeastr-venv-srctest-py38'
        . yeastr-venv-srctest-py38/bin/activate
        set -x
        echo 'pip is always broken on py3.8.20 (and 19 too), patch it'
        sed -i $VIRTUAL_ENV/lib/python3.8/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py -e 's/Sequence\[Candidate\]/Sequence/'
        pip install $CUR_DIR/dist/yeastr-0.0.1-py38-none-any.whl --force-reinstall
        python -m yeastr.packaging_test > ./out/yeastr_test_packaging_py38
        diff ./out/yeastr_test_packaging_py38 $STORE_DIR/out/yeastr_test_packaging

        pip install $LAYOUT_SRC/dist/yeastr_test-0.0.1-py38-none-any.whl --force-reinstall --no-deps
        echo 'Launch same examples with python 3.8'
        python -m yeastr_test.call2comp > ./out/src_call2comp_py38
        python -m yeastr_test.namedloops > ./out/src_namedloops_py38
        python -m yeastr_test.macros > ./out/src_macros_py38
        python -m yeastr_test.test_match_game > ./out/src_match_game_py38
        python -m yeastr_test.macros_test > ./out/src_macros_test_py38
        python -m yeastr_test.backporting_dict_ops > ./out/src_dictops_py38
        set +x ; echo 'deactivate yeastr-venv-srctest-py38'
        deactivate
        set -x

        mkdir -p ./diffs
        diff -C 10 ./out/src_namedloops_{py38,py314} \
            > ./diffs/src_namedloops_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/src_call2comp_{py38,py314} \
            > ./diffs/src_call2comp_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/src_macros_{py38,py314} \
            > ./diffs/src_macros_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/src_macros_test_{py38,py314} \
            > ./diffs/src_macros_test_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/src_match_game_{py38,py314} \
            > ./diffs/src_match_game_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/src_dictops_{py38,py314} \
            > ./diffs/src_dictops_py38_py314 \
            || ((FAILED++)) || true

        for f in `ls $STORE_DIR/out/src*` ; do
            diff -C 10 $f $CI_DIR/out/`basename $f` \
                || ((FAILED++)) || true
        done

        # ----------------------------------------------------------------------
        mkdir -p $LAYOUT_SCRIPT
        cp -r $CUR_DIR/../yeastr-test-script/* $LAYOUT_SCRIPT
        virtualenv -p $PY314 yeastr-venv-script-py314
        set +x ; echo 'activate yeastr-venv-script-py314'
        . yeastr-venv-script-py314/bin/activate
        set -x
        pip install $CUR_DIR/dist/yeastr-0.0.1-py314-none-any.whl --force-reinstall
        pip list
        echo 'Launch some examples'
        python $LAYOUT_SCRIPT/call2comp.py > ./out/script_call2comp_py314
        python $LAYOUT_SCRIPT/namedloops.py > ./out/script_namedloops_py314
        python $LAYOUT_SCRIPT/macros.py > ./out/script_macros_py314
        python $LAYOUT_SCRIPT/test_match_game.py > ./out/script_match_game_py314
        set +x ; echo 'deactivate yeastr-venv-script-py314'
        deactivate
        set -x

        virtualenv -p python3.8 yeastr-venv-script-py38
        set +x ; echo 'activate yeastr-venv-script-py38'
        . yeastr-venv-script-py38/bin/activate
        set -x
        echo 'pip is always broken on py3.8.20 (and 19 too), patch it'
        sed -i $VIRTUAL_ENV/lib/python3.8/site-packages/pip/_internal/resolution/resolvelib/found_candidates.py -e 's/Sequence\[Candidate\]/Sequence/'
        pip install $CUR_DIR/dist/yeastr-0.0.1-py38-none-any.whl --force-reinstall
        echo 'Launch same examples with python 3.8'
        python $LAYOUT_SCRIPT/call2comp.py > ./out/script_call2comp_py38
        python $LAYOUT_SCRIPT/namedloops.py > ./out/script_namedloops_py38
        python $LAYOUT_SCRIPT/macros.py > ./out/script_macros_py38
        # well, the previous run was already using backported code
        #python $LAYOUT_SCRIPT/test_match_game.py > ./out/script_match_game_py38
        set +x ; echo 'deactivate yeastr-venv-script-py38'
        deactivate
        set -x

        mkdir -p ./diffs
        diff -C 10 ./out/script_namedloops_{py38,py314} \
            > ./diffs/script_namedloops_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/script_call2comp_{py38,py314} \
            > ./diffs/script_call2comp_py38_py314 \
            || ((FAILED++)) || true
        diff -C 10 ./out/script_macros_{py38,py314} \
            > ./diffs/script_macros_py38_py314 \
            || ((FAILED++)) || true

        # match without debug
        tail -n `wc -l ./out/src_match_game_py314 | cut -d " " -f 1`\
            ./out/script_match_game_py314\
            > ./out/cleaned_match
        diff -C 10 ./out/cleaned_match ./out/src_match_game_py314\
            > ./diffs/script_match\
            || ((FAILED++)) || true

        for f in `ls $STORE_DIR/out/script*` ; do
            diff -C 10 $f $CI_DIR/out/`basename $f` \
                || ((FAILED++)) || true
        done

        if [ "0" -eq "$FAILED" ] ; then
            echo 'SEEMS OK'
        fi
  ;;
  store)
    for f in \
        src_macros_py3{8,14} \
        src_macros_test_py3{8,14} \
        src_namedloops_py3{8,14} \
        src_call2comp_py3{8,14} \
        src_match_game_py3{8,14} \
        src_dictops_py3{8,14} \
        script_macros_py3{8,14} \
        script_namedloops_py3{8,14} \
        script_call2comp_py3{8,14} \
    ; do
        cp $CI_DIR/out/$f $STORE_DIR/out/$f
    done
  ;;
  --help|help|-h)
    set +x
    echo 'Usage:'
    echo ./local_ci.sh download
    echo "    Latest wheels from pypi (so one can then work offline)"
    echo ./local_ci.sh run
    echo "    Build yeastr and steps below"
    echo ./local_ci.sh run skip-build
    echo "    All the whl files in $WHLS will be installed"
    echo "    Builds yeastr-test-{proj,script}"
    echo "    Runs them and compares output through diff"
    # well, most of the print could be just assert
    # but we also check for differences between python versions
    echo ./local_ci.sh store
    echo "    Save good CI output for the next run"
  ;;
esac
exit $FAILED
